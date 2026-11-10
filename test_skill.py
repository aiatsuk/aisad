"""Release/install/update behavior; no GitHub requests or personal traces."""
import contextlib
import copy
import datetime
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import call, patch
import zipfile

ROOT = Path(__file__).resolve().parent


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


skill = module('asi_skill', ROOT / 'skills/asi/scripts/asi.py')
release = module('asi_release', ROOT / 'scripts/build_release.py')
SANDBOX = {}


def setUpModule():
    # The launcher moves ~/.local/share/aisad when no data directory is set. Every
    # test here, in process or in a child process, sees a temporary home instead.
    SANDBOX['home'] = tempfile.TemporaryDirectory(prefix='asi test home ')
    SANDBOX['environ'] = patch.dict(os.environ, {'HOME': SANDBOX['home'].name})
    SANDBOX['environ'].start()
    for key in [key for key in os.environ if key.startswith(('ASI_', 'AISAD_'))]:
        del os.environ[key]


def tearDownModule():
    SANDBOX['environ'].stop()
    SANDBOX['home'].cleanup()


class MenubarLauncherTests(unittest.TestCase):
    def test_bare_command_launches_without_collector_or_maintenance(self):
        with patch.object(skill, 'launch_menubar', return_value=0) as launch, \
             patch.object(skill, 'maintenance_tasks', side_effect=AssertionError('Unexpected maintenance')):
            self.assertEqual(skill.main(['menubar']), 0)
            self.assertEqual(skill.main(['menubar', '--offline', '--']), 0)
        self.assertEqual(launch.call_count, 2)

    def test_prefers_user_app_and_handles_spaces(self):
        with tempfile.TemporaryDirectory(prefix='asi user ') as home:
            app = Path(home) / 'Applications/ASI.app'
            app.mkdir(parents=True)
            with patch.object(skill.sys, 'platform', 'darwin'), \
                 patch.object(skill.Path, 'home', return_value=Path(home)), \
                 patch.object(skill.subprocess, 'call', return_value=0) as invoke:
                self.assertEqual(skill.launch_menubar(), 0)
            invoke.assert_called_once_with(['/usr/bin/open', str(app)])

    def test_system_and_development_bundle_names(self):
        for app in (Path('/Applications/ASI.app'), Path('/Applications/ASIMenuBar.app')):
            with self.subTest(app=app), patch.object(skill.sys, 'platform', 'darwin'), \
                 patch.object(skill.Path, 'is_dir', autospec=True, side_effect=lambda path: path == app), \
                 patch.object(skill.subprocess, 'call', return_value=0) as invoke:
                self.assertEqual(skill.launch_menubar(), 0)
                invoke.assert_called_once_with(['/usr/bin/open', str(app)])

    def test_registered_app_fallback_and_launch_failure(self):
        new = ['/usr/bin/open', '-b', 'com.aiatsuk.asi.menubar']
        old = ['/usr/bin/open', '-b', 'com.aiatsuk.aisad.menubar']
        with patch.object(skill.sys, 'platform', 'darwin'), \
             patch.object(skill.Path, 'is_dir', return_value=False), \
             patch.object(skill.subprocess, 'call', return_value=0) as invoke:
            self.assertEqual(skill.launch_menubar(), 0)
            invoke.assert_called_once_with(new, stderr=skill.subprocess.DEVNULL)
            # The new bundle ID is not registered: the 1.x app opens instead.
            invoke.reset_mock(); invoke.side_effect = [1, 0]
            self.assertEqual(skill.launch_menubar(), 0)
            self.assertEqual(invoke.call_args_list, [call(new, stderr=skill.subprocess.DEVNULL), call(old)])
            invoke.reset_mock(); invoke.side_effect = None; invoke.return_value = 1
            with self.assertRaisesRegex(skill.UpdateError, 'Install ASI.app'):
                skill.launch_menubar()
            self.assertEqual(invoke.call_args_list, [call(new, stderr=skill.subprocess.DEVNULL), call(old)])

    def test_new_app_names_come_before_the_1x_names(self):
        user, system = Path.home() / 'Applications', Path('/Applications')
        checked = []
        def present(*names):
            def is_dir(path):
                checked.append(path)
                return path in names
            return is_dir
        with patch.object(skill.sys, 'platform', 'darwin'), \
             patch.object(skill.Path, 'is_dir', autospec=True, side_effect=present()), \
             patch.object(skill.subprocess, 'call', return_value=0):
            skill.launch_menubar()
        self.assertEqual(checked, [user / 'ASI.app', system / 'ASI.app', user / 'ASIMenuBar.app', system / 'ASIMenuBar.app',
                                   user / 'AISAD.app', system / 'AISAD.app', user / 'AISADMenuBar.app', system / 'AISADMenuBar.app'])
        for existing, expected in [((user / 'AISAD.app', system / 'ASIMenuBar.app'), system / 'ASIMenuBar.app'),
                                   ((user / 'AISADMenuBar.app', system / 'AISAD.app'), system / 'AISAD.app'),
                                   ((user / 'AISADMenuBar.app',), user / 'AISADMenuBar.app')]:
            with self.subTest(existing=existing), patch.object(skill.sys, 'platform', 'darwin'), \
                 patch.object(skill.Path, 'is_dir', autospec=True, side_effect=present(*existing)), \
                 patch.object(skill.subprocess, 'call', return_value=0) as invoke:
                self.assertEqual(skill.launch_menubar(), 0)
                invoke.assert_called_once_with(['/usr/bin/open', str(expected)])

    def test_unsupported_platform_does_not_open_app(self):
        with patch.object(skill.sys, 'platform', 'linux'), \
             patch.object(skill.subprocess, 'call') as invoke:
            with self.assertRaisesRegex(skill.UpdateError, 'requires macOS'):
                skill.launch_menubar()
            invoke.assert_not_called()


class SkillTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='asi install test ')
        self.root = Path(self.temporary.name)
        self.version, self.assets = release.build(ROOT, self.root / 'dist')
        self.archive = self.assets[1]
        self.manifest, self.files = skill.checked_archive(self.archive.read_bytes(), self.assets[2].read_bytes(), self.archive.name)
        self.installed = self.root / 'profile/skills/asi'
        self.data = self.root / 'local data'

    def tearDown(self):
        self.temporary.cleanup()

    def install(self):
        skill.install_files(self.installed, self.manifest, self.files)

    def newer(self):
        manifest, files = copy.deepcopy(self.manifest), dict(self.files)
        manifest['version'] = '99.0.0'
        files['runtime/agent_usage.py'] = files['runtime/agent_usage.py'].replace(
            ("VERSION = '" + self.version + "'").encode(), b"VERSION = '99.0.0'")
        files['SKILL.md'] += b'\nUpdated instructions.\n'
        files['scripts/asi.py'] += b'\n# Updated helper.\n'
        manifest['files'] = {name: skill.digest(files[name]) for name in manifest['files']}
        files['manifest.json'] = json.dumps(manifest).encode()
        return manifest, files

    def zip(self, files):
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w') as archive:
            for name, data in files.items():
                archive.writestr('asi/' + name, data)
        return output.getvalue()

    def test_deterministic_release_whitelist_and_tag(self):
        _, assets = release.build(ROOT, self.root / 'second', 'v' + self.version)
        self.assertEqual(self.archive.read_bytes(), assets[1].read_bytes())
        self.assertEqual(set(self.files), skill.REQUIRED_FILES | {'manifest.json'})
        with self.assertRaises(ValueError):
            release.build(ROOT, self.root / 'bad', 'v0.0.0')
        for value in ['v2.3.0', '02.3.0', '2.3', '2.3.0-rc1', '../main']:
            with self.assertRaises(skill.UpdateError):
                skill.semver(value)

    def test_integrity_errors(self):
        with self.assertRaises(skill.UpdateError):
            skill.checked_archive(self.archive.read_bytes() + b'changed', self.assets[2].read_bytes(), self.archive.name)
        changed = dict(self.files, **{'SKILL.md': b'Tampered'})
        with self.assertRaises(skill.UpdateError):
            skill.unpack_archive(self.zip(changed))
        malformed = dict(self.files, **{'manifest.json': b'[]'})
        with self.assertRaises(skill.UpdateError):
            skill.unpack_archive(self.zip(malformed))

    def test_unsafe_archives(self):
        for name in ['../escape', '/absolute', 'runtime/../../escape', 'runtime\\escape', 'runtime/C:drive', 'SKILL.MD']:
            with self.subTest(name=name), self.assertRaises(skill.UpdateError):
                skill.unpack_archive(self.zip(dict(self.files, **{name: b'bad'})))
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w') as archive:
            info = zipfile.ZipInfo('asi/link')
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, '/outside')
        with self.assertRaises(skill.UpdateError):
            skill.unpack_archive(output.getvalue())

    def test_complete_update_preserves_external_data(self):
        self.install()
        self.data.mkdir()
        evidence = self.data / 'usage.json'
        evidence.write_text('Local evidence', encoding='utf-8')
        manifest, files = self.newer()
        skill.install_files(self.installed, manifest, files)
        self.assertEqual(skill.read_json(self.installed / 'manifest.json')['version'], '99.0.0')
        for name, contents in files.items():
            self.assertEqual((self.installed / name).read_bytes(), contents)
        self.assertEqual(evidence.read_text(encoding='utf-8'), 'Local evidence')
        with self.assertRaises(skill.UpdateError):
            skill.install_files(self.installed, self.manifest, self.files)

    def test_local_edits_and_unknown_files_are_preserved(self):
        self.install()
        instructions = self.installed / 'SKILL.md'
        instructions.write_bytes(instructions.read_bytes() + b'\nMy changes')
        with self.assertRaisesRegex(skill.UpdateError, 'Local modifications preserved'):
            skill.install_files(self.installed, *self.newer())
        self.assertTrue(instructions.read_bytes().endswith(b'My changes'))
        instructions.write_bytes(self.files['SKILL.md'])
        extra = self.installed / 'private-data.json'
        extra.write_text('Keep me', encoding='utf-8')
        with self.assertRaises(skill.UpdateError):
            skill.install_files(self.installed, *self.newer())
        self.assertEqual(extra.read_text(encoding='utf-8'), 'Keep me')

    def test_explicit_downgrade_cli_preserves_data_and_local_edits(self):
        skill.install_files(self.installed, *self.newer())
        self.data.mkdir()
        report = self.data / 'usage.json'
        report.write_text('Keep local usage', encoding='utf-8')
        command = [sys.executable, '-I', str(ROOT / 'skills/asi/scripts/asi.py'),
                   'install', '--archive', str(self.archive), '--checksum-file', str(self.assets[2]),
                   '--dest', str(self.installed.parent)]
        blocked = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(blocked.returncode, 0)
        self.assertEqual(skill.read_json(self.installed / 'manifest.json')['version'], '99.0.0')
        reset = subprocess.run(command + ['--allow-downgrade'], capture_output=True, text=True)
        self.assertEqual(reset.returncode, 0, reset.stderr)
        self.assertEqual(skill.read_json(self.installed / 'manifest.json')['version'], self.version)
        self.assertEqual(report.read_text(encoding='utf-8'), 'Keep local usage')
        skill.install_files(self.installed, *self.newer())
        instructions = self.installed / 'SKILL.md'
        instructions.write_bytes(instructions.read_bytes() + b'\nLocal changes')
        blocked = subprocess.run(command + ['--allow-downgrade'], capture_output=True, text=True)
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn('Local modifications preserved', blocked.stderr)
        self.assertTrue(instructions.read_bytes().endswith(b'Local changes'))

    def test_reinstall_invalidates_previous_pending_update(self):
        skill.install_files(self.installed, *self.newer())
        skill.atomic_json(skill.state_path(self.installed, self.data), dict(
            installed='99.0.0', latest='99.0.1', available=True, checked_at=skill.time.time()))
        skill.install_files(self.installed, self.manifest, self.files, allow_downgrade=True)
        latest = dict(version=self.version, tag='v' + self.version, archive=self.archive.name)
        with patch.object(skill, 'release_info', return_value=latest) as metadata, \
             patch.object(skill, 'download_release', side_effect=AssertionError('Stale update downloaded')), \
             contextlib.redirect_stderr(io.StringIO()):
            self.assertFalse(skill.update(self.installed, self.data, automatic=True))
        metadata.assert_called_once()
        self.assertEqual(skill.read_json(self.installed / 'manifest.json')['version'], self.version)
        state = skill.read_json(skill.state_path(self.installed, self.data))
        self.assertEqual(state['installed'], self.version)
        self.assertFalse(state['available'])

    def test_failed_swap_restores_installation(self):
        self.install()
        rename = Path.rename
        def fail_stage(path, target):
            if '.stage-' in path.name:
                raise OSError('Simulated replacement failure')
            return rename(path, target)
        with patch.object(Path, 'rename', fail_stage), self.assertRaises(OSError):
            skill.install_files(self.installed, *self.newer())
        self.assertEqual((self.installed / 'manifest.json').read_bytes(), self.files['manifest.json'])
        self.assertEqual((self.installed / 'runtime/agent_usage.py').read_bytes(), self.files['runtime/agent_usage.py'])

    def test_bootstrap_from_clean_github_skill(self):
        for name in skill.BOOTSTRAP_FILES:
            target = self.installed / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(self.files[name])
        self.install()
        self.assertTrue((self.installed / 'runtime/agent_usage.py').is_file())
        skill.verify_replaceable(self.installed, self.files)

    def test_daily_check_then_auto_update_uses_cached_release(self):
        self.install()
        newer = dict(version='99.0.0', tag='v99.0.0', archive='asi-skill-v99.0.0.zip')
        with patch.object(skill, 'release_info', return_value=newer) as metadata:
            result, _ = skill.check_update(self.installed, self.data)
            self.assertTrue(result['available'])
            with patch.object(skill, 'download_release', return_value=self.newer()) as download:
                with contextlib.redirect_stdout(io.StringIO()) as stdout, contextlib.redirect_stderr(io.StringIO()):
                    self.assertTrue(skill.update(self.installed, self.data, automatic=True))
                    self.assertFalse(skill.update(self.installed, self.data, automatic=True))
                self.assertEqual(stdout.getvalue(), '')
                download.assert_called_once_with(newer)
            metadata.assert_called_once()

    def test_failed_checks_and_downloads_are_throttled(self):
        self.install()
        with patch.object(skill, 'release_info', side_effect=OSError('Offline')) as metadata:
            with self.assertRaises(OSError):
                skill.update(self.installed, self.data, automatic=True)
            self.assertFalse(skill.update(self.installed, self.data, automatic=True))
            metadata.assert_called_once()
        skill.state_path(self.installed, self.data).unlink()
        newer = dict(version='99.0.0', tag='v99.0.0', archive='asi-skill-v99.0.0.zip')
        with patch.object(skill, 'release_info', return_value=newer), patch.object(skill, 'download_release', side_effect=OSError('Offline')) as download:
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(OSError):
                skill.update(self.installed, self.data, automatic=True)
            self.assertFalse(skill.update(self.installed, self.data, automatic=True))
            download.assert_called_once()
        skill.verify_replaceable(self.installed, self.files)

    def test_launch_never_waits_on_the_network(self):
        self.install()
        arguments = ['usage', '--data-dir', str(self.data), '--json', '--provider', 'claude']
        with patch.object(skill, '__file__', str(self.installed / 'scripts/asi.py')), \
             patch.object(skill, 'update', side_effect=AssertionError('Foreground network check')), \
             patch.object(skill, 'refresh_prices', side_effect=AssertionError('Foreground price refresh')):
            with patch.object(skill.subprocess, 'Popen') as background, patch.object(skill.subprocess, 'call', return_value=0) as invoke:
                self.assertEqual(skill.main(arguments), 0)
                self.assertEqual(invoke.call_args[0][0], [sys.executable, str(self.installed / 'runtime/agent_usage.py'),
                                 'usage', '--output', str(self.data.resolve() / 'output'), '--json', '--provider', 'claude'])
                command = background.call_args[0][0]
                self.assertEqual(command[1:5], [str(self.installed / 'scripts/asi.py'), 'maintain', '--data-dir', str(self.data.resolve())])
                self.assertEqual(command[5:], ['update', 'prices'])
                self.assertIs(background.call_args[1]['stdin'], skill.subprocess.DEVNULL)
            with patch.object(skill.subprocess, 'Popen', side_effect=AssertionError('Network work offline')), \
                 patch.object(skill.subprocess, 'call', return_value=0):
                self.assertEqual(skill.main(arguments + ['--offline']), 0)

    def test_background_maintenance_runs_update_then_prices(self):
        self.install()
        calls = []
        with patch.object(skill, 'update', side_effect=lambda *a, **k: calls.append(('update', k))), \
             patch.object(skill, 'refresh_prices', side_effect=lambda *a: calls.append(('prices',))), \
             patch.object(skill, '__file__', str(self.installed / 'scripts/asi.py')), \
             contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(skill.main(['maintain', '--data-dir', str(self.data)]), 0)
        self.assertEqual(calls, [('update', {'automatic': True}), ('prices',)])
        # Failures are logged, never raised: the report already ran.
        with patch.object(skill, 'update', side_effect=OSError('Offline')), \
             patch.object(skill, 'refresh_prices'), \
             contextlib.redirect_stderr(io.StringIO()) as errors:
            skill.maintain(self.installed, self.data, ['update'])
        self.assertIn('Update skipped', errors.getvalue())

    def test_every_forwarding_command_reaches_the_collector_with_its_options(self):
        self.install()
        with patch.object(skill, '__file__', str(self.installed / 'scripts/asi.py')), \
             patch.object(skill, 'maintenance_tasks', return_value=[]):
            for command in ('usage', 'analyze', 'statusline', 'collect', 'sessions', 'session', 'prices', 'chart', 'budget', 'forecast', 'menubar',
                            'dashboard', 'fit', 'suggest'):
                with patch.object(skill.subprocess, 'call', return_value=0) as invoke:
                    self.assertEqual(skill.main([command, '--data-dir', str(self.data), '--json', '--refresh']), 0)
                    self.assertEqual(invoke.call_args[0][0][2], command)
                    self.assertIn('--refresh', invoke.call_args[0][0])

    def test_price_refresh_is_daily_offline_aware_and_never_blocks_a_report(self):
        self.install()
        meta = self.data.resolve() / 'output/prices-models-dev.meta.json'
        with patch.object(skill, 'update_due', return_value=False):
            self.assertEqual(skill.maintenance_tasks(self.installed, self.data, 'usage', False), ['prices'])
            self.assertEqual(skill.maintenance_tasks(self.installed, self.data, 'prices', False), [])
            self.assertEqual(skill.maintenance_tasks(self.installed, self.data, 'usage', True), [])
            # A refresh checked today is not repeated.
            meta.parent.mkdir(parents=True, exist_ok=True)
            meta.write_text(json.dumps({'checked_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}))
            self.assertEqual(skill.maintenance_tasks(self.installed, self.data, 'usage', False), [])
            meta.write_text(json.dumps({'checked_at': '2020-01-01T00:00:00+00:00'}))
            self.assertEqual(skill.maintenance_tasks(self.installed, self.data, 'usage', False), ['prices'])
        # The refresh itself keeps stored rates when the network fails.
        with patch.object(skill.subprocess, 'run', side_effect=OSError('No network')), \
             contextlib.redirect_stderr(io.StringIO()) as errors:
            skill.refresh_prices(self.installed / 'runtime/agent_usage.py', self.data.resolve())
        self.assertIn('Price refresh skipped', errors.getvalue())

    def test_update_due_matches_the_automatic_throttle(self):
        self.install()
        self.assertTrue(skill.update_due(self.installed, self.data))
        with patch.object(skill, 'check_update', return_value=({'installed': '9.9.9', 'latest': '9.9.9', 'available': False}, None)), \
             contextlib.redirect_stderr(io.StringIO()):
            skill.update(self.installed, self.data, automatic=True)
        state = skill.read_json(skill.state_path(self.installed, self.data))
        state['installed'] = skill.read_json(self.installed / 'manifest.json').get('version')
        skill.atomic_json(skill.state_path(self.installed, self.data), state)
        self.assertFalse(skill.update_due(self.installed, self.data))

    def test_copied_bundle_cli_and_json_without_dependencies(self):
        installer = ROOT / 'skills/asi/scripts/asi.py'
        destination = self.installed.parent
        run = subprocess.run([sys.executable, '-I', str(installer), 'install', '--archive', str(self.archive),
                              '--checksum-file', str(self.assets[2]), '--dest', str(destination)], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        helper = self.installed / 'scripts/asi.py'
        run = subprocess.run([sys.executable, '-I', str(helper), 'usage', '--offline', '--json', '--include-requests',
                              '--data-dir', str(self.data), '--home', str(self.root / 'empty profile'), '--provider', 'openai'],
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        report = json.loads(run.stdout)
        self.assertEqual(report['version'], self.version)
        self.assertEqual(report['current']['totals']['requests'], 0)
        self.assertEqual(report['current']['requests'], [])
        self.assertFalse((self.data / 'output/dashboard.html').exists())
        for command in ['analyze', 'statusline', 'collect', 'sessions', 'menubar']:
            run = subprocess.run([sys.executable, '-I', str(helper), command, '--offline', '--json',
                                  '--data-dir', str(self.data), '--home', str(self.root / 'empty profile'),
                                  *(['--session', 'Claude:empty'] if command == 'statusline' else [])],
                                 input='{"session_id":"empty"}', capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            result = json.loads(run.stdout)
            self.assertEqual(result['version'], self.version)
            if command == 'analyze':
                self.assertEqual(result['schema_version'], 2)
                self.assertEqual(result['current']['telemetry']['total_records'], 0)
                self.assertNotIn('analysis_rules', result)
            elif command == 'menubar':
                self.assertEqual([p['id'] for p in result['periods']], ['today','week','month'])
                self.assertEqual(result['periods'][2]['budget_usd'], 2000)
                self.assertIsNone(result['periods'][2]['used_percent'])
            elif command == 'statusline':
                self.assertEqual(result['session']['id'], 'Claude:empty')
                self.assertEqual(result['session']['observed_requests'], 0)
        self.assertFalse((self.data / 'output/dashboard.html').exists())
        self.assertFalse((self.data / 'output/status.json').exists())
        run = subprocess.run([sys.executable, '-I', str(helper), 'version'], capture_output=True, text=True)
        self.assertEqual(run.stdout.strip(), 'ASI ' + self.version)
        self.assertEqual(Path.home(), Path(SANDBOX['home'].name))
        self.assertFalse((Path.home() / '.local').exists())

    def test_install_targets_honor_profile_directories(self):
        codex, claude = self.root / 'codex profile', self.root / 'claude profile'
        with patch.dict(os.environ, {'CODEX_HOME': str(codex), 'CLAUDE_CONFIG_DIR': str(claude)}), contextlib.redirect_stdout(io.StringIO()):
            skill.main(['install', '--target', 'both', '--archive', str(self.archive), '--checksum-file', str(self.assets[2])])
        for directory in [codex, claude]:
            self.assertTrue((directory / 'skills/asi/runtime/agent_usage.py').is_file())


    def test_optional_ui_bundle_is_whitelisted_and_rejects_stale_sources(self):
        repository=self.root/'ui-repository';repository.mkdir()
        (repository/'agent_usage.py').write_bytes((ROOT/'agent_usage.py').read_bytes())
        for name in release.SKILL_FILES:
            source=repository/'skills/asi'/name;source.parent.mkdir(parents=True,exist_ok=True)
            source.write_bytes((ROOT/'skills/asi'/name).read_bytes())
        ui=repository/'ui';(ui/'src').mkdir(parents=True);(ui/'dist').mkdir()
        names=['build.ts','package.json','tsconfig.json','bun.lock','src/main.tsx']
        for name in names:(ui/name).write_text('synthetic '+name)
        meta={'schema_version':1,'inputs':{name:release.sha256((ui/name).read_bytes()) for name in names}}
        (ui/'dist/build-meta.json').write_text(json.dumps(meta))
        (ui/'dist/asi-ui.mjs').write_text('// synthetic UI')
        (ui/'dist/THIRD_PARTY_NOTICES.txt').write_text('Synthetic license notice')
        _,assets=release.build(repository,self.root/'ui-dist',with_ui=True)
        manifest,files=skill.checked_archive(assets[1].read_bytes(),assets[2].read_bytes(),assets[1].name)
        self.assertEqual(files['runtime/ui/asi-ui.mjs'],b'// synthetic UI')
        self.assertIn('runtime/ui/THIRD_PARTY_NOTICES.txt',manifest['files'])
        self.assertNotIn('build-meta.json',files)
        (ui/'src/main.tsx').write_text('changed source')
        with self.assertRaisesRegex(ValueError,'rebuild'):release.build(repository,self.root/'stale-dist',with_ui=True)


class SubskillTests(unittest.TestCase):
    """The four Claude Code sub-skills: shipped in the release, linked on install, kept by updates."""
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='asi subskill test ')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.version, self.assets = release.build(ROOT, self.root / 'dist')
        self.manifest, self.files = skill.checked_archive(self.assets[1].read_bytes(), self.assets[2].read_bytes(), self.assets[1].name)
        self.codex, self.claude, self.data = self.root / 'codex', self.root / 'claude', self.root / 'data'
        environment = patch.dict(os.environ, {'CODEX_HOME': str(self.codex), 'CLAUDE_CONFIG_DIR': str(self.claude)})
        environment.start()
        self.addCleanup(environment.stop)
        self.skills = self.claude / 'skills'
        self.installed = self.skills / 'asi'

    def run_main(self, *args):
        with contextlib.redirect_stdout(io.StringIO()) as output, contextlib.redirect_stderr(io.StringIO()) as errors:
            code = skill.main(list(args))
        return code, output.getvalue(), errors.getvalue()

    def install(self, *extra):
        return self.run_main('install', '--archive', str(self.assets[1]), '--checksum-file', str(self.assets[2]), *extra)

    def release_of(self, version, without=()):
        """This tree released as another version, optionally without some sub-skills."""
        files = {name: data for name, data in self.files.items()
                 if name != 'manifest.json' and name.split('/')[:2] not in [['subskills', gone] for gone in without]}
        files['runtime/agent_usage.py'] = files['runtime/agent_usage.py'].replace(
            ("VERSION = '" + self.version + "'").encode(), ("VERSION = '" + version + "'").encode())
        manifest = dict(self.manifest, version=version, files={name: skill.digest(data) for name, data in files.items()})
        files['manifest.json'] = json.dumps(manifest).encode()
        return manifest, files

    def update_to(self, root, manifest, files):
        latest = dict(version=manifest['version'], tag='v' + manifest['version'], archive='asi-skill-v' + manifest['version'] + '.zip')
        with patch.object(skill, 'release_info', return_value=latest), \
             patch.object(skill, 'download_release', return_value=(manifest, files)), \
             contextlib.redirect_stdout(io.StringIO()) as output, contextlib.redirect_stderr(io.StringIO()) as errors:
            self.assertTrue(skill.update(root, self.data))
        return output.getvalue(), errors.getvalue()

    def links(self, directory):
        return sorted(path.name for path in directory.iterdir() if path.is_symlink())

    def assert_linked(self, directory, names=skill.SUBSKILLS):
        self.assertEqual([name for name in self.links(directory) if name.startswith('asi-')], sorted(names))
        for name in names:
            self.assertEqual(os.readlink(str(directory / name)), 'asi/subskills/' + name)
            self.assertEqual((directory / name / 'SKILL.md').read_bytes(), (directory / 'asi/subskills' / name / 'SKILL.md').read_bytes())

    def test_release_ships_the_subskills_and_the_manifest_hashes_them(self):
        with zipfile.ZipFile(self.assets[1]) as archive:
            names = set(archive.namelist())
        for name in skill.SUBSKILLS:
            path = 'subskills/' + name + '/SKILL.md'
            self.assertIn('asi/' + path, names)
            self.assertIn(path, skill.REQUIRED_FILES)
            self.assertEqual(self.manifest['files'][path], skill.digest((ROOT / 'skills/asi' / path).read_bytes()))
        self.assertEqual(sorted(path.parent.name for path in (ROOT / 'skills/asi/subskills').glob('*/SKILL.md')), sorted(skill.SUBSKILLS))
        # A release missing a sub-skill is not a valid release for this launcher.
        manifest, files = self.release_of(self.version, without=('asi-suggest',))
        with self.assertRaisesRegex(skill.UpdateError, 'missing required files'):
            skill.validate_manifest(manifest)

    def test_subskill_texts_name_no_model_and_call_known_commands(self):
        known = set(skill.COLLECTOR_COMMANDS) | {'rules', 'autopilot'}
        for name in skill.SUBSKILLS:
            with self.subTest(name=name):
                text = (ROOT / 'skills/asi/subskills' / name / 'SKILL.md').read_text(encoding='utf-8')
                front, body = text.split('---\n')[1], text.split('---\n', 2)[2]
                fields = dict(line.split(':', 1) for line in front.splitlines() if ':' in line and not line.startswith(' '))
                self.assertEqual(fields['name'].strip(), name)
                self.assertNotIn('model', fields)
                self.assertNotIn('effort', fields)
                self.assertLessEqual(len(fields['description'].strip()), 160)
                self.assertIn('re-write', body)
                self.assertIn("this skill's base directory", body)
                commands = skill.re.findall(r'"\$\{CLAUDE_SKILL_DIR\}/\.\./\.\./scripts/asi\.py" (\S+)', body)
                self.assertTrue(commands)
                self.assertLessEqual(set(commands), known)
                self.assertNotIn('air', ' '.join(commands))

    def test_claude_install_links_each_subskill_and_codex_gets_none(self):
        code, output, errors = self.install('--target', 'both')
        self.assertEqual(code, 0, errors)
        self.assert_linked(self.skills)
        self.assertIn('Linked Claude Code skills /asi-analyze, /asi-autopilot, /asi-suggest, /asi-ultraanalyze', output)
        self.assertEqual(self.links(self.codex / 'skills'), [])
        self.assertEqual(sorted(path.name for path in (self.codex / 'skills').iterdir() if not path.name.startswith('.')), ['asi'])
        # The nested copies stay inside the managed skill and pass its own checks.
        skill.verify_replaceable(self.installed, self.files)
        code, output, errors = self.install('--target', 'claude')
        self.assertEqual((code, errors), (0, ''))
        self.assertNotIn('Linked', output)

    def test_install_keeps_what_is_not_its_link(self):
        self.skills.mkdir(parents=True)
        mine = self.skills / 'asi-suggest'
        mine.mkdir()
        (mine / 'SKILL.md').write_text('my own skill')
        elsewhere = self.root / 'elsewhere'
        elsewhere.mkdir()
        (self.skills / 'asi-analyze').symlink_to(elsewhere, target_is_directory=True)
        (self.skills / 'asi-autopilot').write_text('a file')
        code, output, errors = self.install('--target', 'claude')
        self.assertEqual(code, 0)          # the tool is installed; only these links are missing
        self.assertEqual(len(errors.strip().splitlines()), 4, errors)
        for name in ('asi-suggest', 'asi-analyze', 'asi-autopilot'):
            self.assertIn('Kept ' + str(self.skills / name) + ': it is not a link into asi/subskills/', errors)
        self.assertEqual(errors.strip().splitlines()[-1], '3 sub-skills were not linked (see above); ASI itself is installed')
        self.assertEqual((mine / 'SKILL.md').read_text(), 'my own skill')
        self.assertEqual(os.readlink(str(self.skills / 'asi-analyze')), str(elsewhere))
        self.assertEqual((self.skills / 'asi-autopilot').read_text(), 'a file')
        # The rest is still installed and linked.
        self.assertEqual(os.readlink(str(self.skills / 'asi-ultraanalyze')), 'asi/subskills/asi-ultraanalyze')
        self.assertTrue((self.installed / 'runtime/agent_usage.py').is_file())
        self.assertIn('Installed ASI ' + self.version, output)

    def test_dangling_link_elsewhere_is_kept_and_the_command_line_still_exits_0(self):
        self.skills.mkdir(parents=True)
        (self.skills / 'asi-ultraanalyze').symlink_to('asi/other/asi-ultraanalyze')
        environment = {key: value for key, value in os.environ.items() if not key.startswith(('ASI_', 'AISAD_'))}
        environment.update(HOME=str(self.root / 'home'), ASI_DATA_DIR=str(self.data))
        run = subprocess.run([sys.executable, '-I', str(ROOT / 'skills/asi/scripts/asi.py'), 'install', '--target', 'claude',
                              '--archive', str(self.assets[1]), '--checksum-file', str(self.assets[2])],
                             capture_output=True, text=True, env=environment)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stderr.strip().splitlines(), ['Kept ' + str(self.skills / 'asi-ultraanalyze') + ': it is not a link into '
                                                           'asi/subskills/; move it away and install again to get /asi-ultraanalyze',
                                                           '1 sub-skill was not linked (see above); ASI itself is installed'])
        self.assertIn('Installed ASI ' + self.version, run.stdout)
        self.assertEqual(os.readlink(str(self.skills / 'asi-ultraanalyze')), 'asi/other/asi-ultraanalyze')
        self.assertEqual([os.readlink(str(self.skills / name)) for name in ('asi-analyze', 'asi-autopilot', 'asi-suggest')],
                         ['asi/subskills/asi-analyze', 'asi/subskills/asi-autopilot', 'asi/subskills/asi-suggest'])
        self.assertFalse((self.root / 'home/.local').exists())

    def test_reinstall_keeps_correct_links_and_repairs_its_own(self):
        self.assertEqual(self.install('--target', 'claude')[0], 0)
        kept = os.lstat(str(self.skills / 'asi-suggest')).st_ino
        (self.skills / 'asi-analyze').unlink()
        (self.skills / 'asi-analyze').symlink_to('asi/subskills/asi-suggest')       # ours, wrong sub-skill
        (self.skills / 'asi-autopilot').unlink()
        (self.skills / 'asi-autopilot').symlink_to(self.installed / 'subskills/asi-autopilot')  # ours, absolute: correct
        (self.skills / 'asi-ultraanalyze').unlink()                                 # removed by hand
        code, output, errors = self.install('--target', 'claude')
        self.assertEqual((code, errors), (0, ''))
        self.assertEqual(os.lstat(str(self.skills / 'asi-suggest')).st_ino, kept)
        self.assertEqual(os.readlink(str(self.skills / 'asi-analyze')), 'asi/subskills/asi-analyze')
        self.assertEqual(os.readlink(str(self.skills / 'asi-autopilot')), str(self.installed / 'subskills/asi-autopilot'))
        self.assertEqual(os.readlink(str(self.skills / 'asi-ultraanalyze')), 'asi/subskills/asi-ultraanalyze')
        self.assertIn('/asi-analyze, /asi-ultraanalyze in', output)
        self.assertEqual([path.name for path in self.skills.iterdir() if '.link-' in path.name], [])

    def test_update_from_a_build_without_subskills_creates_the_links(self):
        skill.install_files(self.installed, *self.release_of(self.version, without=skill.SUBSKILLS))
        self.assertEqual(self.links(self.skills), [])
        output, errors = self.update_to(self.installed, *self.release_of('99.0.0'))
        self.assertEqual(skill.read_json(self.installed / 'manifest.json')['version'], '99.0.0')
        self.assert_linked(self.skills)
        self.assertIn('Linked Claude Code skills', output)
        self.assertNotIn('Kept', errors)

    def test_a_link_failure_does_not_undo_or_hide_a_finished_update(self):
        self.assertEqual(self.install('--target', 'claude')[0], 0)
        with patch.object(skill, 'link_subskills', side_effect=PermissionError('Operation not permitted')):
            _, errors = self.update_to(self.installed, *self.release_of('99.0.0'))
        self.assertIn('Updated, but could not link the sub-skills: Operation not permitted', errors)
        self.assertEqual(skill.read_json(self.installed / 'manifest.json')['version'], '99.0.0')
        state = skill.read_json(skill.state_path(self.installed, self.data))
        self.assertEqual((state['installed'], state['available']), ('99.0.0', False))

    def test_self_update_keeps_links_and_removes_one_for_a_dropped_subskill(self):
        self.assertEqual(self.install('--target', 'claude')[0], 0)
        stranger = self.skills / 'unrelated'
        stranger.symlink_to('asi/missing/unrelated')
        manifest, files = self.release_of('99.0.0', without=('asi-autopilot',))
        output, errors = self.update_to(self.installed, manifest, files)
        self.assertEqual(errors.count('Kept'), 0, errors)
        self.assertFalse((self.skills / 'asi-autopilot').exists() or (self.skills / 'asi-autopilot').is_symlink())
        self.assertIn('Removed ' + str(self.skills / 'asi-autopilot'), output)
        self.assert_linked(self.skills, [name for name in skill.SUBSKILLS if name != 'asi-autopilot'])
        self.assertTrue(stranger.is_symlink())  # dangling, but not ours
        skill.verify_replaceable(self.installed, files)

    def test_codex_and_unlinked_installs_get_no_links_on_update(self):
        self.assertEqual(self.install('--target', 'codex')[0], 0)
        codex_skill = self.codex / 'skills/asi'
        self.assertFalse(skill.links_wanted(codex_skill))
        self.update_to(codex_skill, *self.release_of('99.0.0'))
        self.assertEqual(self.links(codex_skill.parent), [])
        # A custom destination installed for Claude keeps its links through updates.
        custom = self.root / 'custom skills'
        self.assertEqual(self.install('--dest', str(custom), '--target', 'claude')[0], 0)
        self.assert_linked(custom)
        self.assertTrue(skill.links_wanted(custom / 'asi'))
        self.update_to(custom / 'asi', *self.release_of('99.0.0'))
        self.assert_linked(custom)
        self.assertIn(b'99.0.0', (custom / 'asi/runtime/agent_usage.py').read_bytes())
        # --dest without --target claude stays unlinked.
        plain = self.root / 'plain skills'
        self.assertEqual(self.install('--dest', str(plain))[0], 0)
        self.assertEqual(self.links(plain), [])

    def test_locally_modified_subskill_is_preserved(self):
        self.assertEqual(self.install('--target', 'claude')[0], 0)
        changed = self.installed / 'subskills/asi-suggest/SKILL.md'
        changed.write_bytes(changed.read_bytes() + b'\nMy own rule.\n')
        with self.assertRaisesRegex(skill.UpdateError, 'Local modifications preserved: subskills/asi-suggest/SKILL.md'):
            skill.install_files(self.installed, *self.release_of('99.0.0'))
        self.assertTrue(changed.read_bytes().endswith(b'My own rule.\n'))
        changed.write_bytes(self.files['subskills/asi-suggest/SKILL.md'])
        extra = self.installed / 'subskills/my-skill/SKILL.md'
        extra.parent.mkdir()
        extra.write_text('mine')
        with self.assertRaisesRegex(skill.UpdateError, 'subskills/my-skill/SKILL.md'):
            skill.install_files(self.installed, *self.release_of('99.0.0'))
        self.assertEqual(extra.read_text(), 'mine')

    def test_a_subskill_runs_the_launcher_through_its_link(self):
        self.assertEqual(self.install('--target', 'claude')[0], 0)
        through_link = self.skills / 'asi-suggest/../../scripts/asi.py'
        # Only the sub-skill link is followed; the rest of the path stays as given (here /var, not /private/var).
        self.assertEqual(skill.skill_root(str(through_link)), self.installed)
        self.assertEqual(skill.skill_root(str(self.installed / 'scripts/asi.py')), self.installed)
        environment = {key: value for key, value in os.environ.items() if not key.startswith(('ASI_', 'AISAD_'))}
        environment.update(HOME=str(self.root / 'home'), ASI_DATA_DIR=str(self.data), ASI_AUTO_UPDATE='0', ASI_AUTO_PRICES='0')
        for args, expected in ((['version'], 'ASI ' + self.version), (['autopilot', 'status'], str(self.claude / 'CLAUDE.md'))):
            run = subprocess.run([sys.executable, '-I', str(through_link)] + args, capture_output=True, text=True, env=environment)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn(expected, run.stdout)
        # Forwarded commands reach the installed collector with the installed skill as root.
        with patch.object(skill, '__file__', str(through_link)), patch.object(skill, 'maintenance_tasks', return_value=[]), \
             patch.object(skill.subprocess, 'call', return_value=0) as invoke:
            self.assertEqual(skill.main(['suggest', '--data-dir', str(self.data), '--session', 'abc']), 0)
        self.assertEqual(invoke.call_args[0][0][1:3], [str(self.installed / 'runtime/agent_usage.py'), 'suggest'])
        self.assertEqual(invoke.call_args[0][0][-2:], ['--session', 'abc'])
        self.assertFalse((self.root / 'home/.local').exists())

    def test_a_symlinked_skill_directory_is_refused_on_both_routes(self):
        real = self.root / 'dotfiles/skills/asi'
        skill.install_files(real, self.manifest, self.files)
        self.skills.mkdir(parents=True)
        self.installed.symlink_to(real, target_is_directory=True)
        for name in skill.SUBSKILLS:
            (self.skills / name).symlink_to('asi/subskills/' + name)
        before = {path.relative_to(real).as_posix(): path.read_bytes() for path in real.rglob('*') if path.is_file()}
        newer = self.release_of('99.0.0')
        latest = dict(version='99.0.0', tag='v99.0.0', archive='asi-skill-v99.0.0.zip')
        routes = {'direct': self.installed / 'scripts/asi.py', 'sub-skill': self.skills / 'asi-suggest/../../scripts/asi.py'}
        for route, script in routes.items():
            with self.subTest(route=route):
                self.assertTrue(script.is_file())
                root = skill.skill_root(str(script))
                self.assertEqual(root, self.installed)
                with self.assertRaisesRegex(skill.UpdateError, 'symlinked skill directory'):
                    skill.verify_replaceable(root, newer[1])
                # The background update that a launch on this route starts refuses as well.
                with patch.object(skill, '__file__', str(script)), patch.object(skill, 'release_info', return_value=latest), \
                     patch.object(skill, 'download_release', return_value=newer), \
                     contextlib.redirect_stderr(io.StringIO()) as errors:
                    self.assertEqual(skill.main(['maintain', '--data-dir', str(self.data / route), 'update']), 0)
                self.assertIn('Update skipped; keeping installed code: Refusing to replace a symlinked skill directory', errors.getvalue())
        self.assertTrue(self.installed.is_symlink())
        self.assertEqual({path.relative_to(real).as_posix(): path.read_bytes() for path in real.rglob('*') if path.is_file()}, before)

    def test_stepping_out_of_a_link_follows_only_that_link(self):
        base = self.root / 'tree'
        (base / 'real/inner').mkdir(parents=True)
        (base / 'skills').mkdir()
        (base / 'skills/top').symlink_to(base / 'real', target_is_directory=True)        # a link that is kept
        (base / 'skills/hop').symlink_to('top/inner')                                      # the one '..' leaves
        (base / 'skills/chain').symlink_to('hop')                                          # a link to a link
        for path, expected in ((base / 'skills/hop/../x', base / 'skills/top/x'),       # 'top' stays a link
                               (base / 'skills/chain/../../y', base / 'y'),             # the second '..' leaves 'top'
                               (base / 'skills/top/../z', base / 'z')):
            self.assertEqual(skill.step_out(path), expected)
            self.assertEqual(os.path.realpath(str(expected)), os.path.realpath(str(path)))   # where the system goes too
        (base / 'skills/loop').symlink_to('loop')
        with self.assertRaises(OSError):
            skill.step_out(base / 'skills/loop/../x')


def clean_environment(**values):
    """os.environ without ASI_/AISAD_ settings, plus the given values."""
    environment = {key: value for key, value in os.environ.items() if not key.startswith(('ASI_', 'AISAD_'))}
    environment.update(values)
    return patch.dict(os.environ, environment, clear=True)


class SettingsAndDataDirectoryTests(unittest.TestCase):
    """1.x (AISAD) names and the 1.x data directory keep working after the rename."""
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='asi data test ')
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name) / 'home'
        self.new, self.old = self.home / '.local/share/asi', self.home / '.local/share/aisad'

    def test_new_setting_wins_then_the_1x_name_then_the_default(self):
        with clean_environment():
            self.assertIsNone(skill.setting('AUTO_UPDATE'))
            self.assertEqual(skill.setting('AUTO_UPDATE', '1'), '1')
        for values, expected in [({'AISAD_AUTO_UPDATE': '0'}, '0'), ({'ASI_AUTO_UPDATE': '1', 'AISAD_AUTO_UPDATE': '0'}, '1'),
                                 ({'ASI_AUTO_UPDATE': '', 'AISAD_AUTO_UPDATE': '0'}, '0'), ({'ASI_AUTO_UPDATE': '', 'AISAD_AUTO_UPDATE': ''}, '1')]:
            with self.subTest(values=values), clean_environment(**values):
                self.assertEqual(skill.setting('AUTO_UPDATE', '1'), expected)

    def test_maintenance_switches_accept_both_names(self):
        root, data = self.home / 'skill', self.home / 'data'
        with patch.object(skill, 'update_due', return_value=True), patch.object(skill, 'prices_due', return_value=True):
            for values, expected in [({}, ['update', 'prices']), ({'AISAD_AUTO_UPDATE': '0'}, ['prices']),
                                     ({'AISAD_AUTO_PRICES': '0'}, ['update']), ({'ASI_AUTO_UPDATE': '0', 'ASI_AUTO_PRICES': '0'}, []),
                                     ({'ASI_AUTO_UPDATE': '1', 'AISAD_AUTO_UPDATE': '0'}, ['update', 'prices'])]:
                with self.subTest(values=values), clean_environment(**values):
                    self.assertEqual(skill.maintenance_tasks(root, data, 'usage', False), expected)

    def test_data_directory_option_then_new_then_1x_variable(self):
        self.old.mkdir(parents=True)
        first, second, third = (self.home / name for name in ('first', 'second', 'third'))
        with patch.object(skill.Path, 'home', return_value=self.home):
            with clean_environment(ASI_DATA_DIR=str(first), AISAD_DATA_DIR=str(second)):
                self.assertEqual(skill.data_directory(), first.resolve())
                self.assertEqual(skill.data_directory(str(third)), third.resolve())
            with clean_environment(AISAD_DATA_DIR=str(second)):
                self.assertEqual(skill.data_directory(), second.resolve())
        # A configured directory never moves the default one.
        self.assertTrue(self.old.is_dir()); self.assertFalse(self.new.exists())

    def test_1x_data_directory_moves_once_and_keeps_its_files(self):
        (self.old / 'output').mkdir(parents=True)
        (self.old / 'output/budget.json').write_text('{"monthly_budget_usd": 3210}')
        with patch.object(skill.Path, 'home', return_value=self.home), clean_environment(), \
             contextlib.redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(skill.data_directory(), self.new.resolve())
            self.assertIn('Moved local data from ' + str(self.old), errors.getvalue())
            # The old path stays as a link, so a status line script that reads it keeps working.
            self.assertTrue(self.old.is_symlink())
            self.assertEqual((self.old / 'output/budget.json').read_text(), '{"monthly_budget_usd": 3210}')
            self.assertEqual((self.new / 'output/budget.json').read_text(), '{"monthly_budget_usd": 3210}')
            # Later runs find the new directory and stay quiet.
            self.assertEqual(skill.data_directory(), self.new.resolve())
            # Even if the link is replaced by a fresh 1.x directory, nothing moves again.
            self.old.unlink(); self.old.mkdir()
            self.assertEqual(skill.data_directory(), self.new.resolve())
        self.assertEqual(errors.getvalue().count('Moved'), 1)
        self.assertTrue(self.old.is_dir())

    def test_1x_path_that_is_already_a_link_is_used_where_it_points(self):
        elsewhere = self.home / 'elsewhere'
        elsewhere.mkdir(parents=True)
        self.old.parent.mkdir(parents=True)
        self.old.symlink_to(elsewhere, target_is_directory=True)
        with patch.object(skill.Path, 'home', return_value=self.home), clean_environment(), \
             contextlib.redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(skill.data_directory(), elsewhere.resolve())
        self.assertEqual(errors.getvalue(), '')
        self.assertTrue(self.old.is_symlink()); self.assertFalse(self.new.exists())

    def test_new_directory_without_an_old_one_is_used_as_is(self):
        with patch.object(skill.Path, 'home', return_value=self.home), clean_environment(), \
             contextlib.redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(skill.data_directory(), self.new.resolve())
        self.assertEqual(errors.getvalue(), '')
        self.assertFalse(self.old.exists())

    def test_failed_move_keeps_using_the_1x_directory(self):
        self.old.mkdir(parents=True)
        with patch.object(skill.Path, 'home', return_value=self.home), clean_environment(), \
             patch.object(skill.Path, 'rename', side_effect=PermissionError('Operation not permitted')), \
             contextlib.redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(skill.data_directory(), self.old.resolve())
        self.assertIn('Keeping local data in ' + str(self.old), errors.getvalue())
        self.assertIn('Operation not permitted', errors.getvalue())
        self.assertTrue(self.old.is_dir()); self.assertFalse(self.new.exists())

    def test_move_lost_to_another_launcher_uses_the_new_directory(self):
        self.old.mkdir(parents=True)
        rename = Path.rename
        def raced(path, target):
            rename(path, target)  # The other launcher moved it first ...
            raise FileNotFoundError('No such file or directory')  # ... so this attempt fails.
        with patch.object(skill.Path, 'home', return_value=self.home), clean_environment(), \
             patch.object(skill.Path, 'rename', autospec=True, side_effect=raced), \
             contextlib.redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(skill.data_directory(), self.new.resolve())
        self.assertNotIn('Keeping', errors.getvalue())

    def test_reading_commands_never_move_the_directory_and_writing_ones_do(self):
        (self.old / 'output').mkdir(parents=True)
        skill.atomic_json(self.old / 'model-rules.json', {'hint': False, 'autopilot': True})
        environment = {key: value for key, value in os.environ.items() if not key.startswith(('ASI_', 'AISAD_'))}
        environment.update(HOME=str(self.home), CLAUDE_CONFIG_DIR=str(self.home / 'claude'))
        launch = lambda *args: subprocess.run([sys.executable, '-I', str(ROOT / 'skills/asi/scripts/asi.py'), *args],
                                              capture_output=True, text=True, env=environment)
        for args in (['version'], ['rules'], ['rules', 'status'], ['rules', 'show'], ['autopilot'], ['autopilot', 'status'],
                     ['autopilot', 'show']):
            with self.subTest(args=args):
                run = launch(*args)
                self.assertEqual((run.returncode, run.stderr), (0, ''))
                self.assertTrue(self.old.is_dir() and not self.old.is_symlink())
                self.assertFalse(self.new.exists() or self.new.is_symlink())
        # While the 1.x directory is the only one, reading commands read it.
        self.assertIn('autopilot: on', launch('autopilot', 'status').stdout)
        self.assertIn('first-message hint: off; autopilot: on', launch('rules', 'status').stdout)
        # A command that writes to the data directory moves it once.
        run = launch('rules', 'off')
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn('Moved local data from ' + str(self.old), run.stderr)
        self.assertTrue((self.new / 'output').is_dir()); self.assertTrue(self.old.is_symlink())
        self.assertEqual(skill.read_json(self.new / 'model-rules.json'), {'hint': False, 'autopilot': True})
        self.assertEqual((launch('autopilot', 'status').stderr, launch('version').stderr), ('', ''))

    def test_reading_without_moving_picks_new_then_old_then_the_new_path(self):
        with patch.object(skill.Path, 'home', return_value=self.home), clean_environment(), \
             contextlib.redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(skill.data_directory(move=False), self.new.resolve())
            self.assertFalse(self.new.parent.exists())                     # nothing is created
            self.old.mkdir(parents=True)
            self.assertEqual(skill.data_directory(move=False), self.old.resolve())
            self.new.mkdir()
            self.assertEqual(skill.data_directory(move=False), self.new.resolve())
            self.assertTrue(self.old.is_dir() and not self.old.is_symlink())
        self.assertEqual(errors.getvalue(), '')


class LegacyInstallTests(unittest.TestCase):
    """Installing ASI next to an AISAD 1.x skill or terminal command."""
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='asi legacy test ')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.version, assets = release.build(ROOT, self.root / 'dist')
        self.install = ['install', '--archive', str(assets[1]), '--checksum-file', str(assets[2])]
        self.skills = self.root / 'profile/skills'
        self.old = self.skills / 'aisad'

    def legacy(self):
        """A 1.x release install as its installer left it, with a bytecode cache."""
        files = {'SKILL.md': b'---\nname: aisad\n---\n', 'agents/openai.yaml': b'interface: {}\n',
                 'scripts/aisad.py': b'# 1.x launcher\n', 'runtime/agent_usage.py': b"VERSION = '1.5.2'\n"}
        for name, data in files.items():
            (self.old / name).parent.mkdir(parents=True, exist_ok=True)
            (self.old / name).write_bytes(data)
        manifest = dict(schema=1, repository='aiatsuk/aisad', version='1.5.2', files={name: skill.digest(data) for name, data in files.items()})
        (self.old / 'manifest.json').write_text(json.dumps(manifest))
        (self.old / 'scripts/__pycache__').mkdir()
        (self.old / 'scripts/__pycache__/aisad.cpython-314.pyc').write_bytes(b'cache')
        return files

    def run_install(self, *extra):
        with contextlib.redirect_stdout(io.StringIO()) as output, contextlib.redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(skill.main(self.install + ['--dest', str(self.skills)] + list(extra)), 0)
        self.assertTrue((self.skills / 'asi/runtime/agent_usage.py').is_file())
        return output.getvalue(), errors.getvalue()

    def test_unmodified_1x_skill_is_removed(self):
        self.legacy()
        output, errors = self.run_install()
        self.assertFalse(self.old.exists())
        self.assertIn('Removed the previous AISAD skill at ' + str(self.old), output)
        self.assertEqual(errors, '')
        self.assertEqual([path.name for path in self.skills.iterdir() if not path.name.startswith('.')], ['asi'])
        self.assertEqual([path.name for path in self.skills.iterdir() if '.removed-' in path.name], [])

    def test_the_1x_update_lock_goes_with_the_removed_skill_only(self):
        lock = self.skills / '.aisad.update.lock'
        self.legacy()
        lock.write_bytes(b'')
        self.run_install()
        self.assertFalse(self.old.exists())
        self.assertFalse(lock.exists() or lock.is_symlink())
        self.assertTrue((self.skills / '.asi.update.lock').exists())        # the new install's own lock stays
        # A 1.x skill that is kept keeps its lock.
        self.legacy()
        (self.old / 'notes.txt').write_text('keep me')
        _, errors = self.run_install()
        self.assertIn('Kept the previous AISAD skill', errors)
        self.assertTrue(self.old.is_dir())
        self.assertFalse(lock.exists())                                     # the check made no new stray lock
        # A lock that was there before the install stays.
        lock.write_bytes(b'')
        self.run_install()
        self.assertTrue(self.old.is_dir() and lock.exists())

    def test_failed_delete_of_the_1x_skill_is_reported_and_install_succeeds(self):
        self.legacy()
        with patch.object(skill.shutil, 'rmtree', side_effect=PermissionError('Operation not permitted')):
            output, errors = self.run_install()
        self.assertFalse(self.old.exists())
        self.assertIn('Removed the previous AISAD skill', output)
        leftovers = [path for path in self.skills.iterdir() if path.name.startswith('.aisad.removed-')]
        self.assertEqual(len(leftovers), 1)
        self.assertIn('Could not delete its files at ' + str(leftovers[0]), errors)
        self.assertTrue((leftovers[0] / 'manifest.json').is_file())

    def test_1x_skill_with_local_changes_is_kept_with_one_line(self):
        for change in ('edit', 'extra', 'missing', 'no manifest', 'other repository'):
            with self.subTest(change=change):
                shutil.rmtree(self.skills, ignore_errors=True)
                self.legacy()
                if change == 'edit':
                    (self.old / 'SKILL.md').write_bytes(b'My own notes\n')
                elif change == 'extra':
                    (self.old / 'notes.txt').write_text('keep me')
                elif change == 'missing':
                    (self.old / 'agents/openai.yaml').unlink()
                elif change == 'no manifest':
                    (self.old / 'manifest.json').unlink()
                else:
                    manifest = json.loads((self.old / 'manifest.json').read_text())
                    (self.old / 'manifest.json').write_text(json.dumps(dict(manifest, repository='someone/else')))
                before = sorted(path.relative_to(self.old).as_posix() for path in self.old.rglob('*'))
                output, errors = self.run_install()
                self.assertTrue(self.old.is_dir())
                self.assertEqual(sorted(path.relative_to(self.old).as_posix() for path in self.old.rglob('*')), before)
                self.assertEqual(len(errors.strip().splitlines()), 1, errors)
                self.assertIn('Kept the previous AISAD skill at ' + str(self.old), errors)
                self.assertNotIn('Removed', output)

    def test_symlinked_or_locked_1x_skill_is_kept(self):
        target = self.root / 'elsewhere'
        target.mkdir()
        self.skills.mkdir(parents=True)
        self.old.symlink_to(target, target_is_directory=True)
        _, errors = self.run_install()
        self.assertTrue(self.old.is_symlink()); self.assertTrue(target.is_dir())
        self.assertIn('not a plain directory', errors)
        self.old.unlink()
        self.legacy()
        # A 1.x update in flight holds the same lock file.
        with (self.skills / '.aisad.update.lock').open('a+b') as lock:
            skill.fcntl.flock(lock, skill.fcntl.LOCK_EX | skill.fcntl.LOCK_NB)
            _, errors = self.run_install()
        self.assertTrue((self.old / 'manifest.json').is_file())
        self.assertIn('Another ASI update is running', errors)
        self.assertEqual(len(errors.strip().splitlines()), 1, errors)

    def test_no_1x_skill_means_no_message(self):
        output, errors = self.run_install()
        self.assertNotIn('AISAD', output + errors)
        self.assertFalse(self.old.exists())

    def test_1x_terminal_command_becomes_an_alias(self):
        bin_dir = self.root / 'bin dir'
        bin_dir.mkdir()
        old_command = bin_dir / 'aisad'
        old_command.write_text('#!/bin/sh\n# AISAD CLI launcher\nexec python3 /old/skills/aisad/scripts/aisad.py "$@"\n')
        old_command.chmod(0o755)
        output, errors = self.run_install('--cli-dir', str(bin_dir))
        command = bin_dir / 'asi'
        self.assertIn('# ASI CLI launcher', command.read_text())
        self.assertIn(str(self.skills / 'asi/scripts/asi.py'), command.read_text())
        alias = old_command.read_text()
        self.assertTrue(alias.startswith('#!/bin/sh\n# AISAD CLI launcher\n'))
        self.assertIn('exec ' + skill.shlex.quote(str(command)) + ' "$@"', alias)
        self.assertNotIn('/old/skills', alias)
        self.assertTrue(os.access(old_command, os.X_OK))
        self.assertIn('now runs ' + str(command), output)
        self.assertEqual(errors, '')
        # The alias really runs the new command; a temporary home keeps real data untouched.
        environment = {key: value for key, value in os.environ.items() if not key.startswith(('ASI_', 'AISAD_'))}
        environment.update(HOME=str(self.root / 'home'), ASI_DATA_DIR=str(self.root / 'data'))
        run = subprocess.run([str(old_command), 'version'], capture_output=True, text=True, env=environment)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout.strip(), 'ASI ' + self.version)
        self.assertFalse((self.root / 'home/.local').exists())
        # Installing again leaves both commands as they are.
        self.run_install('--cli-dir', str(bin_dir))
        self.assertEqual(old_command.read_text(), alias)

    def test_unrelated_or_symlinked_aisad_command_is_left_alone(self):
        bin_dir = self.root / 'bin'
        bin_dir.mkdir()
        unrelated = '#!/bin/sh\necho my own aisad\n'
        (bin_dir / 'aisad').write_text(unrelated)
        _, errors = self.run_install('--cli-dir', str(bin_dir))
        self.assertEqual((bin_dir / 'aisad').read_text(), unrelated)
        self.assertEqual(errors, '')
        (bin_dir / 'aisad').unlink()
        target = self.root / 'real-aisad'
        target.write_text('#!/bin/sh\n# AISAD CLI launcher\nexec true\n')
        (bin_dir / 'aisad').symlink_to(target)
        self.run_install('--cli-dir', str(bin_dir))
        self.assertEqual(target.read_text(), '#!/bin/sh\n# AISAD CLI launcher\nexec true\n')
        (bin_dir / 'aisad').unlink()
        # No 1.x command: none is created.
        self.run_install('--cli-dir', str(bin_dir))
        self.assertFalse((bin_dir / 'aisad').exists())

    def test_edited_1x_command_is_left_alone_with_one_line(self):
        bin_dir = self.root / 'bin'
        bin_dir.mkdir()
        old_command = bin_dir / 'aisad'
        launcher = '#!/bin/sh\n# AISAD CLI launcher\nexec python3 /old/skills/aisad/scripts/aisad.py "$@"\n'
        edited = (launcher + 'echo done\n',                                                      # a line added
                  launcher.replace('exec python3', 'exec python3 -X dev'),                       # an option added
                  launcher.replace('/old/skills/aisad/scripts/aisad.py', '/old/my-aisad.py'),     # another script
                  launcher.replace('/old/skills', 'old/skills'),                                 # a relative path
                  launcher.replace('"$@"', '"$@" --json'),
                  launcher.replace('\n', '\r\n'),
                  '#!/bin/sh\n# AISAD CLI launcher\n# Alias for the asi command\nexec /usr/local/bin/asi --offline "$@"\n')
        for text in edited:
            with self.subTest(text=text):
                old_command.write_bytes(text.encode())
                output, errors = self.run_install('--cli-dir', str(bin_dir))
                self.assertEqual(old_command.read_bytes(), text.encode())
                self.assertEqual(errors.splitlines(), ['Left the aisad command at ' + str(old_command) +
                                                       ' as it is: it was changed after the AISAD installer wrote it'])
                self.assertNotIn('now runs', output)
        # What 1.x wrote, a path with spaces included, is still made an alias.
        quoted = '#!/bin/sh\n# AISAD CLI launcher\nexec python3 ' + skill.shlex.quote('/my skills/aisad/scripts/aisad.py') + ' "$@"\n'
        old_command.write_text(quoted)
        output, errors = self.run_install('--cli-dir', str(bin_dir))
        self.assertEqual(errors, '')
        self.assertIn('# Alias for the asi command', old_command.read_text())
        self.assertIn('now runs', output)

    def test_unwritable_1x_command_is_reported_and_install_still_succeeds(self):
        bin_dir = self.root / 'bin'
        bin_dir.mkdir()
        legacy = '#!/bin/sh\n# AISAD CLI launcher\nexec python3 /old/skills/aisad/scripts/aisad.py "$@"\n'
        (bin_dir / 'aisad').write_text(legacy)
        (bin_dir / 'aisad').chmod(0o444)
        self.addCleanup((bin_dir / 'aisad').chmod, 0o644)
        _, errors = self.run_install('--cli-dir', str(bin_dir))
        self.assertIn('Could not point ' + str(bin_dir / 'aisad'), errors)
        self.assertEqual((bin_dir / 'aisad').read_text(), legacy)
        self.assertTrue((bin_dir / 'asi').is_file())


if __name__ == '__main__':
    unittest.main()
