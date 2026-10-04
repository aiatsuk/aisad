"""Release version checks and changelog notes; temporary files only for failures."""
import contextlib
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent

spec = importlib.util.spec_from_file_location('aisad_release_tool', ROOT / 'scripts/release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)

CHANGELOG = """# Changelog

## 2.0.0 — 2026-10-04

- First change.

- Second change after a blank line.

## 1.9.0 — 2026-09-01

- Older change.
"""


def run(*args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = release.main(list(args))
    return code, out.getvalue(), err.getvalue()


class ReleaseToolTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.write_version('2.0.0')
        (self.root / 'CHANGELOG.md').write_text(CHANGELOG, encoding='utf-8')

    def write_version(self, version):
        (self.root / 'agent_usage.py').write_text(
            '"""Synthetic collector."""\nVERSION = ' + repr(version) + '\n', encoding='utf-8')

    def test_repository_versions_agree(self):
        version = release.read_version(ROOT, release.PRIMARY_VERSION_FILE)
        self.assertEqual(release.check(ROOT, 'v' + version), version)
        code, out, err = run('check', '--tag', 'v' + version)
        self.assertEqual((code, err), (0, ''))
        self.assertIn(version, out)

    def test_version_command_prints_primary_version(self):
        code, out, _ = run('--root', str(self.root), 'version')
        self.assertEqual((code, out), (0, '2.0.0\n'))

    def test_agreement_passes(self):
        self.assertEqual(release.check(self.root, 'v2.0.0'), '2.0.0')
        self.assertEqual(run('--root', str(self.root), 'check', '--tag', 'v2.0.0')[0], 0)

    def test_mismatched_version_file_fails(self):
        self.write_version('1.9.9')
        code, _, err = run('--root', str(self.root), 'check', '--tag', 'v2.0.0')
        self.assertEqual(code, 1)
        self.assertIn('agent_usage.py has version 1.9.9', err)

    def test_missing_changelog_section_fails(self):
        self.write_version('2.1.0')
        code, _, err = run('--root', str(self.root), 'check', '--tag', 'v2.1.0')
        self.assertEqual(code, 1)
        self.assertIn('no section "## 2.1.0 — ', err)

    def test_malformed_tag_fails(self):
        for tag in ('2.0.0', 'v2.0', 'v02.0.0', 'v2.0.0-rc1'):
            with self.subTest(tag=tag):
                code, _, err = run('--root', str(self.root), 'check', '--tag', tag)
                self.assertEqual(code, 1)
                self.assertIn('vX.Y.Z', err)

    def test_notes_return_exact_section_body(self):
        self.assertEqual(release.changelog_section(self.root, '2.0.0'),
                         '- First change.\n\n- Second change after a blank line.')
        self.assertEqual(release.changelog_section(self.root, '1.9.0'), '- Older change.')
        code, out, _ = run('--root', str(self.root), 'notes', '--tag', 'v2.0.0')
        self.assertEqual((code, out), (0, '- First change.\n\n- Second change after a blank line.\n'))

    def test_command_line_entry_point(self):
        result = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/release.py'), '--root', str(self.root),
                                 'notes', '--tag', 'v1.9.0'], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual((result.returncode, result.stdout), (0, '- Older change.\n'))


if __name__ == '__main__':
    unittest.main()
