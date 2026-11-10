"""The rules block and autopilot switch in Claude Code's CLAUDE.md; temporary directories only."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
LAUNCHER = ROOT / 'skills/asi/scripts/asi.py'

spec = importlib.util.spec_from_file_location('asi_rules_launcher', LAUNCHER)
skill = importlib.util.module_from_spec(spec)
spec.loader.exec_module(skill)

SANDBOX = {}


def setUpModule():
    # Nothing here may reach the real home: the launcher moves ~/.local/share/aisad and
    # these commands write CLAUDE.md. Every test also sets its own directories.
    SANDBOX['home'] = tempfile.TemporaryDirectory(prefix='asi rules home ')
    home = Path(SANDBOX['home'].name)
    SANDBOX['environ'] = patch.dict(os.environ, {
        'HOME': str(home), 'CLAUDE_CONFIG_DIR': str(home / 'claude'), 'CODEX_HOME': str(home / 'codex'),
        'ASI_DATA_DIR': str(home / 'data'), 'ASI_AUTO_UPDATE': '0', 'ASI_AUTO_PRICES': '0'})
    SANDBOX['environ'].start()
    for key in [key for key in os.environ if key.startswith('AISAD_')]:
        del os.environ[key]


def tearDownModule():
    SANDBOX['environ'].stop()
    SANDBOX['home'].cleanup()


ON = {'hint': True, 'autopilot': True}
HINT = {'hint': True, 'autopilot': False}
OFF = {'hint': False, 'autopilot': False}
AIR_BLOCK = ('<!-- air:begin -->\n# AIR: model and effort\n\nManaged by `air rules` (~/pr/air); edits inside this block '
             'are not kept.\n\nUse `/air-suggest`.\n<!-- air:end -->\n')


class Tmp(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='asi rules test ')
        self.addCleanup(temporary.cleanup)
        self.dir = Path(temporary.name)
        self.data = self.dir / 'data'

    def asi(self, *args, extra_env=None):
        """The launcher in a child process, with CLAUDE.md at <dir>/CLAUDE.md."""
        env = {key: value for key, value in os.environ.items() if not key.startswith(('ASI_', 'AISAD_'))}
        env.update(HOME=str(self.dir / 'home'), CLAUDE_CONFIG_DIR=str(self.dir), CODEX_HOME=str(self.dir / 'codex'),
                   ASI_DATA_DIR=str(self.data), ASI_AUTO_UPDATE='0', ASI_AUTO_PRICES='0')
        env.pop('CLAUDE_SESSION_ID', None)
        env.update(extra_env or {})
        return subprocess.run([sys.executable, '-I', str(LAUNCHER), *args], capture_output=True, text=True, env=env, cwd=self.dir)


class RulesTest(Tmp):
    """Ported from the AIR prototype's RulesTest, renamed to ASI."""

    def test_add_replace_remove_keep_surrounding_text(self):
        base = '<!-- engram:begin -->\nmemory\n<!-- engram:end -->\n\n# Working rules\n\n- one\n'
        with_hint = skill.render_rules(base, HINT)
        self.assertTrue(with_hint.startswith(base.rstrip('\n')))
        self.assertEqual(with_hint.count(skill.RULES_BEGIN), 1)
        self.assertNotIn('ASI autopilot: on', with_hint)
        both = skill.render_rules(with_hint, ON)
        self.assertIn('ASI autopilot: on', both)
        self.assertEqual(skill.render_rules(both, ON), both)             # idempotent
        self.assertEqual(skill.render_rules(both, HINT), with_hint)      # switching back restores
        self.assertEqual(skill.render_rules(both, OFF), base)            # removal restores the original

    def test_block_in_the_middle_and_empty_file(self):
        text = 'top\n\n' + skill.rules_block(HINT) + '\nbottom\n'
        self.assertEqual(skill.render_rules(text, OFF), 'top\n\nbottom\n')
        self.assertEqual(skill.render_rules('', OFF), '')
        self.assertEqual(skill.render_rules('', HINT), skill.rules_block(HINT))
        self.assertEqual(skill.render_rules(skill.rules_block(HINT), OFF), '')
        only_auto = skill.rules_block({'hint': False, 'autopilot': True})
        self.assertIn('# ASI autopilot: on', only_auto)
        self.assertNotIn('## ASI', only_auto)

    def test_block_texts_are_renamed(self):
        block = skill.rules_block(ON)
        self.assertTrue(block.startswith('<!-- asi:begin -->\n# ASI: model and effort\n\nManaged by `asi rules`; '
                                         'edits inside this block are not kept.\n'))
        self.assertIn('\n## ASI autopilot: on\n', block)
        self.assertIn('`/asi-suggest` gives the full version', block)
        self.assertNotIn('AIR', block)
        self.assertNotIn('/air-', block)

    def test_malformed_markers_are_refused(self):
        for bad in (skill.RULES_BEGIN + '\nx\n', 'x\n' + skill.RULES_END + '\n', skill.RULES_END + '\n' + skill.RULES_BEGIN + '\n',
                    skill.rules_block(HINT) * 2):
            with self.subTest(bad=bad), self.assertRaises(skill.RulesError):
                skill.render_rules(bad, ON)

    def test_adjacent_reversed_markers_are_refused(self):
        with self.assertRaises(skill.RulesError):
            skill.render_rules('top\n' + skill.RULES_END + skill.RULES_BEGIN + '\nbottom\n', HINT)

    def test_crlf_file_keeps_its_line_endings(self):
        base = 'a\r\nb\r\n'
        on = skill.render_rules(base, ON)
        self.assertTrue(on.startswith(base))
        self.assertNotIn('\n', on.replace('\r\n', ''))
        self.assertEqual(skill.render_rules(on, OFF), base)
        md = self.dir / 'CLAUDE.md'
        md.write_bytes(base.encode())
        self.assertEqual(self.asi('rules', 'on').returncode, 0)
        self.assertTrue(md.read_bytes().startswith(base.encode()))
        self.assertNotIn(b'\n', md.read_bytes().replace(b'\r\n', b''))
        self.assertEqual(self.asi('rules', 'off').returncode, 0)
        self.assertEqual(md.read_bytes(), base.encode())

    def test_symlinked_file_stays_a_link(self):
        real = self.dir / 'real' / 'C.md'
        real.parent.mkdir()
        real.write_text('# Real\n')
        (self.dir / 'CLAUDE.md').symlink_to(real)
        self.assertEqual(self.asi('rules', 'on').returncode, 0)
        self.assertTrue((self.dir / 'CLAUDE.md').is_symlink())
        self.assertIn('ASI: model and effort', real.read_text())
        self.assertTrue(real.read_text().startswith('# Real\n'))

    def test_dangling_link_gets_its_target_and_a_looping_link_is_refused(self):
        md = self.dir / 'CLAUDE.md'
        md.symlink_to('dotfiles/CLAUDE.md')
        self.assertEqual(self.asi('rules', 'on').returncode, 0)
        self.assertTrue(md.is_symlink())
        self.assertEqual((self.dir / 'dotfiles/CLAUDE.md').read_text(), skill.rules_block(HINT))
        md.unlink()
        md.symlink_to('loop.md')
        (self.dir / 'loop.md').symlink_to('CLAUDE.md')
        r = self.asi('autopilot', 'on')
        self.assertEqual(r.returncode, 1)
        self.assertTrue('loops' in r.stderr and 'Traceback' not in r.stderr, r.stderr[-300:])
        self.assertTrue(md.is_symlink() and (self.dir / 'loop.md').is_symlink())
        self.assertIn('autopilot: off', self.asi('autopilot', 'status').stdout)

    def test_new_file_is_readable_and_bad_inputs_do_not_crash(self):
        self.assertEqual(self.asi('rules', 'on').returncode, 0)
        md = self.dir / 'CLAUDE.md'
        self.assertEqual(md.stat().st_mode & 0o777, 0o644)
        for malformed in ('[]', '{not json', '{"hint": "yes", "autopilot": null}'):
            with self.subTest(state=malformed):
                (self.data / 'model-rules.json').write_text(malformed)
                run = self.asi('rules', 'status')
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertNotIn('Traceback', run.stderr)
        md.write_bytes(b'caf\xe9 not utf-8\n')
        r = self.asi('autopilot', 'on')
        self.assertEqual(r.returncode, 1)
        self.assertTrue('UTF-8' in r.stderr and 'Traceback' not in r.stderr, r.stderr[-300:])
        self.assertEqual(md.read_bytes(), b'caf\xe9 not utf-8\n')

    def test_state_and_file_stay_in_step_when_one_write_fails(self):
        md = self.dir / 'CLAUDE.md'
        md.write_text('# Mine\n')
        self.assertEqual(self.asi('rules', 'on').returncode, 0)
        os.chmod(self.data, 0o500)
        self.addCleanup(os.chmod, self.data, 0o700)
        before = md.read_text()
        r = self.asi('autopilot', 'on')
        self.assertEqual(r.returncode, 1)
        self.assertTrue('cannot save' in r.stderr and 'Traceback' not in r.stderr, r.stderr[-300:])
        self.assertEqual(md.read_text(), before)               # the block was not changed either

    def test_failed_file_write_restores_the_saved_state(self):
        md = self.dir / 'CLAUDE.md'
        md.write_text(skill.RULES_BEGIN + '\nhalf a block\n')
        self.assertEqual(self.asi('autopilot', 'on').returncode, 1)
        self.assertEqual(skill.read_json(self.data / 'model-rules.json'), {'hint': True, 'autopilot': False})

    def test_cli_autopilot_round_trip(self):
        md = self.dir / 'CLAUDE.md'
        md.write_text('# Mine\n')
        r = self.asi('autopilot', 'on')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('ASI autopilot: on', md.read_text())
        self.assertIn('Rules to follow in this session', r.stdout)
        self.assertIn(skill.AUTOPILOT, r.stdout)
        self.assertIn('autopilot: on', self.asi('autopilot', 'status').stdout)
        r = self.asi('autopilot', 'off')
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.splitlines()[-1], "Autopilot is off. From now on in this session, stop choosing models and "
                         "effort for subagents on ASI's behalf; follow agent definitions and the session defaults.")
        self.assertNotIn('ASI autopilot: on', md.read_text())
        self.assertIn('ASI: model and effort', md.read_text())          # the hint stays
        self.assertEqual(self.asi('rules', 'off').returncode, 0)
        self.assertEqual(md.read_text(), '# Mine\n')

    def test_cli_refuses_broken_file_and_keeps_state(self):
        md = self.dir / 'CLAUDE.md'
        md.write_text(skill.RULES_BEGIN + '\nhalf a block\n')
        r = self.asi('autopilot', 'on')
        self.assertEqual(r.returncode, 1)
        self.assertIn('markers', r.stderr)
        self.assertIn(str(md), r.stderr)
        self.assertNotIn('Traceback', r.stderr)
        self.assertEqual(md.read_text(), skill.RULES_BEGIN + '\nhalf a block\n')
        self.assertIn('autopilot: off', self.asi('autopilot', 'status').stdout)
        md.write_text('x\n' + skill.RULES_END + '\n' + skill.RULES_BEGIN + '\n')
        r = self.asi('rules', 'on')
        self.assertEqual(r.returncode, 1)
        self.assertIn('the end marker comes before the begin marker', r.stderr)

    def test_cli_unwritable_target(self):
        (self.dir / 'CLAUDE.md').write_text('file, not a folder')
        r = self.asi('autopilot', 'on', extra_env={'CLAUDE_CONFIG_DIR': str(self.dir / 'CLAUDE.md')})
        self.assertEqual(r.returncode, 1)
        self.assertIn('cannot write', r.stderr)
        self.assertNotIn('Traceback', r.stderr)
        self.assertEqual((self.dir / 'CLAUDE.md').read_text(), 'file, not a folder')


class AirBlockTest(Tmp):
    """A block left by the AIR prototype is taken over, never duplicated."""

    def test_air_block_is_replaced_in_place(self):
        base = '# Mine\n\n' + AIR_BLOCK + '\n# After\n'
        on = skill.render_rules(base, HINT)
        self.assertEqual(on, '# Mine\n\n' + skill.rules_block(HINT) + '\n# After\n')
        self.assertNotIn('air:', on)
        self.assertEqual(skill.render_rules(on, HINT), on)
        self.assertEqual(skill.render_rules(on, OFF), '# Mine\n\n# After\n')

    def test_switching_off_removes_the_air_block_too(self):
        self.assertEqual(skill.render_rules('top\n\n' + AIR_BLOCK + '\nbottom\n', OFF), 'top\n\nbottom\n')
        self.assertEqual(skill.render_rules(AIR_BLOCK, OFF), '')

    def test_file_with_both_blocks_keeps_one(self):
        ours = skill.rules_block(HINT)
        for text in ('top\n\n' + AIR_BLOCK + '\nmid\n\n' + ours + '\nbottom\n',
                     'top\n\n' + ours + '\nmid\n\n' + AIR_BLOCK + '\nbottom\n'):
            with self.subTest(order=text.index('air:') < text.index('asi:')):
                on = skill.render_rules(text, ON)
                self.assertNotIn('air:', on)
                self.assertEqual(on.count(skill.RULES_BEGIN), 1)
                self.assertEqual(on.count(skill.RULES_END), 1)
                self.assertIn('ASI autopilot: on', on)
                self.assertTrue(on.startswith('top\n\n'))
                self.assertIn('mid\n', on)
                self.assertTrue(on.endswith('\nbottom\n'))
                self.assertEqual(skill.render_rules(on, ON), on)
                self.assertEqual(skill.render_rules(on, OFF), 'top\n\nmid\n\nbottom\n')

    def test_crlf_air_block(self):
        text = 'a\r\n\r\n' + AIR_BLOCK.replace('\n', '\r\n') + 'b\r\n'
        on = skill.render_rules(text, ON)
        self.assertNotIn('air:', on)
        self.assertNotIn('\n', on.replace('\r\n', ''))
        self.assertEqual(skill.render_rules(on, OFF), 'a\r\n\r\nb\r\n')

    def test_broken_or_overlapping_air_markers_are_refused(self):
        bad = (skill.AIR_BEGIN + '\nhalf\n', 'x\n' + skill.AIR_END + '\n' + skill.AIR_BEGIN + '\n', AIR_BLOCK * 2,
               skill.AIR_BEGIN + '\n' + skill.rules_block(HINT) + skill.AIR_END + '\n')
        for text in bad:
            with self.subTest(text=text), self.assertRaises(skill.RulesError) as caught:
                skill.render_rules(text, ON)
            self.assertTrue('AIR' in str(caught.exception), caught.exception)

    def test_cli_takes_the_air_block_over_once(self):
        md = self.dir / 'CLAUDE.md'
        md.write_text('# Mine\n\n' + AIR_BLOCK)
        r = self.asi('rules', 'on')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(md.read_text(), '# Mine\n\n' + skill.rules_block(HINT))
        self.assertIn('No change needed', self.asi('rules', 'on').stdout)
        self.assertIn('hint present', self.asi('rules', 'status').stdout)
        md.write_text('# Mine\n\n' + AIR_BLOCK + '\n' + skill.rules_block(HINT))
        self.assertEqual(self.asi('autopilot', 'on').returncode, 0)
        self.assertEqual(md.read_text(), '# Mine\n\n' + skill.rules_block(ON))


class LauncherCommandTest(Tmp):
    """rules and autopilot are handled by the launcher: messages, exit codes, nothing else runs."""

    def test_status_and_show_change_nothing(self):
        for args in (('rules',), ('rules', 'status'), ('rules', 'show'), ('autopilot',), ('autopilot', 'status'), ('autopilot', 'show')):
            with self.subTest(args=args):
                r = self.asi(*args)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(r.stderr, '')
        self.assertFalse((self.dir / 'CLAUDE.md').exists())
        self.assertFalse(self.data.exists())
        self.assertEqual(self.asi('autopilot', 'show').stdout, skill.AUTOPILOT + '\n')
        self.assertEqual(self.asi('rules', 'show').stdout, skill.rules_block(HINT) + '\n')
        status = self.asi('rules', 'status').stdout.splitlines()
        self.assertEqual(status, ['first-message hint: on; autopilot: off',
                                  'block in ' + str(self.dir / 'CLAUDE.md') + ': hint absent, autopilot absent'])
        self.assertEqual(self.asi('autopilot').stdout.strip(),
                         'autopilot: off (rules block in ' + str(self.dir / 'CLAUDE.md') + ': absent)')

    def test_on_off_apply_messages(self):
        md = self.dir / 'CLAUDE.md'
        r = self.asi('rules', 'on')
        self.assertEqual(r.stdout, 'Updated ' + str(md) + '\n')
        self.assertEqual(self.asi('rules', 'apply').stdout, 'No change needed in ' + str(md) + '\n')
        md.write_text('')
        self.assertEqual(self.asi('rules', 'apply').stdout, 'Updated ' + str(md) + '\n')
        self.assertEqual(md.read_text(), skill.rules_block(HINT))
        self.assertEqual(self.asi('rules', 'off').returncode, 0)
        self.assertEqual(self.asi('rules', 'show').stdout, '(nothing switched on)\n')
        self.assertEqual(md.read_text(), '')
        self.assertEqual(skill.read_json(self.data / 'model-rules.json'), {'hint': False, 'autopilot': False})

    def test_bad_arguments_exit_2(self):
        for args, message in ((('rules', 'maybe'), 'invalid choice'), (('autopilot', 'apply'), 'invalid choice'),
                              (('autopilot', 'on', '--json'), 'unrecognized arguments'), (('rules', 'on', 'off'), 'unrecognized arguments')):
            with self.subTest(args=args):
                r = self.asi(*args)
                self.assertEqual(r.returncode, 2)
                self.assertIn(message, r.stderr)
        self.assertFalse((self.dir / 'CLAUDE.md').exists())

    def test_no_collector_update_or_network(self):
        with patch.dict(os.environ, {'CLAUDE_CONFIG_DIR': str(self.dir), 'ASI_AUTO_UPDATE': '1', 'ASI_AUTO_PRICES': '1'}), \
             patch.object(skill, 'maintenance_tasks', side_effect=AssertionError('maintenance')), \
             patch.object(skill, 'update', side_effect=AssertionError('update')), \
             patch.object(skill, 'fetch', side_effect=AssertionError('network')), \
             patch.object(skill.subprocess, 'call', side_effect=AssertionError('collector')), \
             patch.object(skill.subprocess, 'Popen', side_effect=AssertionError('background')), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(skill.main(['autopilot', 'on', '--data-dir', str(self.data)]), 0)
            self.assertEqual(skill.main(['rules', 'status', '--data-dir', str(self.data)]), 0)
            self.assertEqual(skill.main(['autopilot', 'off', '--data-dir', str(self.data)]), 0)
        self.assertIn('Autopilot is on for new sessions', output.getvalue())
        self.assertIn('first-message hint: on; autopilot: on', output.getvalue())
        self.assertIn('ASI: model and effort', (self.dir / 'CLAUDE.md').read_text())

    def test_data_directory_inside_the_skill_is_refused(self):
        r = self.asi('rules', 'on', '--data-dir', str(LAUNCHER.parent))
        self.assertEqual(r.returncode, 1)
        self.assertIn('outside the installed skill', r.stderr)
        self.assertFalse((self.dir / 'CLAUDE.md').exists())


if __name__ == '__main__':
    unittest.main()
