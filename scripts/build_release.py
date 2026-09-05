#!/usr/bin/env python3
"""Build reproducible release assets from an explicit source whitelist."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SKILL_FILES = ('SKILL.md', 'agents/openai.yaml', 'scripts/aisad.py')


def version_from_source(source):
    tree = ast.parse(source.decode('utf-8'))
    versions = [ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == 'VERSION' for target in node.targets)]
    if len(versions) != 1 or not re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', versions[0]):
        raise ValueError('agent_usage.py must define one stable semantic VERSION')
    return versions[0]


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def build(root, output, tag=None):
    source = (root / 'agent_usage.py').read_bytes()
    version = version_from_source(source)
    if tag and tag != 'v' + version:
        raise ValueError('Release tag must match agent_usage.py VERSION: v' + version)
    payloads = {}
    for name in SKILL_FILES:
        path = root / 'skills/aisad' / name
        if path.is_symlink():
            raise ValueError('Release source must not be a symlink: ' + name)
        payloads[name] = path.read_bytes()
    payloads['runtime/agent_usage.py'] = source
    manifest = dict(schema=1, repository='aiatsuk/aisad', version=version,
                    files={name: sha256(data) for name, data in sorted(payloads.items())})
    payloads['manifest.json'] = (json.dumps(manifest, indent=2, sort_keys=True) + '\n').encode('utf-8')
    output.mkdir(parents=True, exist_ok=True)
    (output / 'agent_usage.py').write_bytes(source)
    archive_path = output / ('aisad-skill-v' + version + '.zip')
    with zipfile.ZipFile(archive_path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(payloads.items()):
            info = zipfile.ZipInfo('aisad/' + name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    assets = [output / 'agent_usage.py', archive_path]
    (output / 'SHA256SUMS').write_text(''.join(sha256(path.read_bytes()) + '  ' + path.name + '\n' for path in assets), encoding='utf-8')
    return version, assets + [output / 'SHA256SUMS']


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--output', default=str(ROOT / 'dist'))
    cli.add_argument('--tag', help='Require this release tag to match the source version')
    args = cli.parse_args()
    version, files = build(ROOT, Path(args.output).expanduser().resolve(), args.tag)
    print('Built AISAD ' + version)
    for path in files:
        print(path)


if __name__ == '__main__':
    main()
