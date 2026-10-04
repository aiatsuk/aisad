#!/usr/bin/env python3
"""Check release versions and print release notes from CHANGELOG.md.

Commands:
  version                 print the version from agent_usage.py
  check --tag vX.Y.Z      fail unless every version file and CHANGELOG.md agree with the tag
  notes --tag vX.Y.Z      print the CHANGELOG.md section body for the tag
"""
import argparse
import ast
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]

# Files that carry the release version. agent_usage.py VERSION is the source of
# truth; scripts/build_release.py and the skill tests read it from there.
VERSION_FILES = ('agent_usage.py',)
PRIMARY_VERSION_FILE = VERSION_FILES[0]
CHANGELOG = 'CHANGELOG.md'

SEMVER = r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)'


class ReleaseError(Exception):
    pass


def version_from_python(path):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    versions = [ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == 'VERSION' for target in node.targets)]
    if len(versions) != 1 or not isinstance(versions[0], str):
        raise ReleaseError(path.name + ' must define exactly one string VERSION')
    return versions[0]


def read_version(root, name):
    path = Path(root) / name
    if not path.is_file():
        raise ReleaseError('Version file is missing: ' + name)
    return version_from_python(path)


def tag_version(tag):
    match = re.fullmatch('v(' + SEMVER + ')', tag or '')
    if not match:
        raise ReleaseError('Tag must look like vX.Y.Z: ' + repr(tag))
    return match.group(1)


def changelog_section(root, version):
    path = Path(root) / CHANGELOG
    if not path.is_file():
        raise ReleaseError(CHANGELOG + ' is missing')
    lines = path.read_text(encoding='utf-8').splitlines()
    heading = '## ' + version + ' — '
    for index, line in enumerate(lines):
        if line.startswith(heading):
            body = []
            for following in lines[index + 1:]:
                if following.startswith('## '):
                    break
                body.append(following)
            return '\n'.join(body).strip('\n')
    raise ReleaseError(CHANGELOG + ' has no section "' + heading + 'YYYY-MM-DD"')


def check(root, tag):
    version = tag_version(tag)
    problems = []
    for name in VERSION_FILES:
        try:
            found = read_version(root, name)
        except ReleaseError as error:
            problems.append(str(error))
            continue
        if found != version:
            problems.append(name + ' has version ' + found + ', tag ' + tag + ' needs ' + version)
    try:
        if not changelog_section(root, version).strip():
            problems.append(CHANGELOG + ' section for ' + version + ' is empty')
    except ReleaseError as error:
        problems.append(str(error))
    if problems:
        raise ReleaseError('\n'.join(problems))
    return version


def main(argv=None):
    cli = argparse.ArgumentParser(description='Check release versions and print release notes.')
    commands = cli.add_subparsers(dest='command', required=True)
    commands.add_parser('version', help='print the version from ' + PRIMARY_VERSION_FILE)
    for name, text in (('check', 'verify every version file and the changelog match the tag'),
                       ('notes', 'print the changelog section body for the tag')):
        command = commands.add_parser(name, help=text)
        command.add_argument('--tag', required=True, help='release tag, vX.Y.Z')
    cli.add_argument('--root', default=str(ROOT), help=argparse.SUPPRESS)
    args = cli.parse_args(argv)
    root = Path(args.root)
    try:
        if args.command == 'version':
            print(read_version(root, PRIMARY_VERSION_FILE))
        elif args.command == 'check':
            version = check(root, args.tag)
            print('Release ' + args.tag + ' matches ' + ', '.join(VERSION_FILES) + ' and ' + CHANGELOG
                  + ' (version ' + version + ')')
        else:
            print(changelog_section(root, tag_version(args.tag)))
    except ReleaseError as error:
        print('release: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
