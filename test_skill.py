"""Release/install/update behavior; no GitHub requests or personal traces."""
import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parent


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


skill = module('aisad_skill', ROOT / 'skills/aisad/scripts/aisad.py')
release = module('aisad_release', ROOT / 'scripts/build_release.py')


class SkillTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='aisad install test ')
        self.root = Path(self.temporary.name)
        self.version, self.assets = release.build(ROOT, self.root / 'dist')
        self.archive = self.assets[1]
        self.manifest, self.files = skill.checked_archive(self.archive.read_bytes(), self.assets[2].read_bytes(), self.archive.name)
        self.installed = self.root / 'profile/skills/aisad'
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
        files['scripts/aisad.py'] += b'\n# Updated helper.\n'
        manifest['files'] = {name: skill.digest(files[name]) for name in manifest['files']}
        files['manifest.json'] = json.dumps(manifest).encode()
        return manifest, files

    def zip(self, files):
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w') as archive:
            for name, data in files.items():
                archive.writestr('aisad/' + name, data)
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
            info = zipfile.ZipInfo('aisad/link')
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
        newer = dict(version='99.0.0', tag='v99.0.0', archive='aisad-skill-v99.0.0.zip')
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
        newer = dict(version='99.0.0', tag='v99.0.0', archive='aisad-skill-v99.0.0.zip')
        with patch.object(skill, 'release_info', return_value=newer), patch.object(skill, 'download_release', side_effect=OSError('Offline')) as download:
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(OSError):
                skill.update(self.installed, self.data, automatic=True)
            self.assertFalse(skill.update(self.installed, self.data, automatic=True))
            download.assert_called_once()
        skill.verify_replaceable(self.installed, self.files)

    def test_usage_launch_offline_fallback_and_new_helper(self):
        self.install()
        arguments = ['usage', '--data-dir', str(self.data), '--json', '--provider', 'claude']
        with patch.object(skill, '__file__', str(self.installed / 'scripts/aisad.py')):
            with patch.object(skill, 'update', side_effect=OSError('Offline')), patch.object(skill.subprocess, 'call', return_value=0) as invoke:
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(skill.main(arguments), 0)
                self.assertEqual(invoke.call_args[0][0], [sys.executable, str(self.installed / 'runtime/agent_usage.py'),
                                 'usage', '--output', str(self.data.resolve() / 'output'), '--json', '--provider', 'claude'])
            with patch.object(skill, 'update', return_value=True), patch.object(skill.subprocess, 'call', return_value=0) as invoke:
                self.assertEqual(skill.main(arguments), 0)
                self.assertIn('--offline', invoke.call_args[0][0])
                self.assertEqual(invoke.call_args[0][0][2], 'usage')
            with patch.object(skill, 'update', side_effect=AssertionError('Network check used')), patch.object(skill.subprocess, 'call', return_value=0):
                self.assertEqual(skill.main(arguments + ['--offline']), 0)

    def test_copied_bundle_cli_and_json_without_dependencies(self):
        installer = ROOT / 'skills/aisad/scripts/aisad.py'
        destination = self.installed.parent
        run = subprocess.run([sys.executable, '-I', str(installer), 'install', '--archive', str(self.archive),
                              '--checksum-file', str(self.assets[2]), '--dest', str(destination)], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        helper = self.installed / 'scripts/aisad.py'
        run = subprocess.run([sys.executable, '-I', str(helper), 'usage', '--offline', '--json', '--include-requests',
                              '--data-dir', str(self.data), '--home', str(self.root / 'empty profile'), '--provider', 'openai'],
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        report = json.loads(run.stdout)
        self.assertEqual(report['version'], self.version)
        self.assertEqual(report['current']['totals']['requests'], 0)
        self.assertEqual(report['current']['requests'], [])
        self.assertFalse((self.data / 'output/dashboard.html').exists())
        run = subprocess.run([sys.executable, '-I', str(helper), 'version'], capture_output=True, text=True)
        self.assertEqual(run.stdout.strip(), 'AISAD ' + self.version)

    def test_install_targets_honor_profile_directories(self):
        codex, claude = self.root / 'codex profile', self.root / 'claude profile'
        with patch.dict(os.environ, {'CODEX_HOME': str(codex), 'CLAUDE_CONFIG_DIR': str(claude)}), contextlib.redirect_stdout(io.StringIO()):
            skill.main(['install', '--target', 'both', '--archive', str(self.archive), '--checksum-file', str(self.assets[2])])
        for directory in [codex, claude]:
            self.assertTrue((directory / 'skills/aisad/runtime/agent_usage.py').is_file())


if __name__ == '__main__':
    unittest.main()
