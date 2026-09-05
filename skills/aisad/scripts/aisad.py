#!/usr/bin/env python3
"""Install, update and run AISAD without transmitting usage data. Python 3.9+."""
import argparse
import ast
from contextlib import contextmanager
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
import zipfile

REPOSITORY = 'aiatsuk/aisad'
API = 'https://api.github.com/repos/' + REPOSITORY
RELEASES = 'https://github.com/' + REPOSITORY + '/releases/download/'
CHECK_INTERVAL = 24 * 60 * 60
MAX_DOWNLOAD = 10 * 1024 * 1024
REQUIRED_FILES = {'SKILL.md', 'agents/openai.yaml', 'scripts/aisad.py', 'runtime/agent_usage.py'}
BOOTSTRAP_FILES = REQUIRED_FILES - {'runtime/agent_usage.py'}


class UpdateError(Exception):
    pass


def semver(value):
    match = re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', str(value))
    if not match:
        raise UpdateError('Expected a stable version such as 2.3.0')
    return tuple(map(int, match.groups()))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as output:
            json.dump(value, output, indent=2)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_json(path):
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def fetch(url, limit=MAX_DOWNLOAD):
    # Public metadata/code only. No authorization, device metadata or telemetry headers.
    request = urllib.request.Request(url, headers={'User-Agent': 'AISAD-skill', 'Accept': 'application/json'})
    with urllib.request.urlopen(request, timeout=15) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise UpdateError('Release download exceeds the size limit')
    return data


def release_info(version=None):
    if version:
        semver(version)
    endpoint = '/releases/tags/v' + version if version else '/releases/latest'
    release = json.loads(fetch(API + endpoint, 1024 * 1024))
    if not isinstance(release, dict):
        raise UpdateError('Malformed release metadata')
    tag = release.get('tag_name', '')
    if not isinstance(tag, str):
        raise UpdateError('Malformed release tag')
    candidate = tag[1:] if tag.startswith('v') else ''
    semver(candidate)
    if release.get('draft') or release.get('prerelease') or (version and version != candidate):
        raise UpdateError('Expected a published stable release with the requested version')
    name = 'aisad-skill-v' + candidate + '.zip'
    assets = release.get('assets', [])
    if not isinstance(assets, list):
        raise UpdateError('Malformed release assets')
    assets = {asset.get('name') for asset in assets if isinstance(asset, dict) and isinstance(asset.get('name'), str)}
    if not {name, 'SHA256SUMS'} <= assets:
        raise UpdateError('Release is missing the skill archive or checksums')
    return {'version': candidate, 'tag': tag, 'archive': name}


def checked_archive(data, checksums, name):
    if len(data) > MAX_DOWNLOAD:
        raise UpdateError('Release archive exceeds the size limit')
    entries = {}
    for line in checksums.decode('utf-8').splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  (\S+)', line)
        if not match or match[2] in entries:
            raise UpdateError('Malformed or duplicate release checksum')
        entries[match[2]] = match[1]
    if entries.get(name) != digest(data):
        raise UpdateError('Release archive checksum mismatch')
    return unpack_archive(data)


def safe_path(name):
    path = PurePosixPath(name)
    if not name or '\\' in name or ':' in name or path.is_absolute() or any(p in ('', '.', '..') for p in name.split('/')):
        raise UpdateError('Unsafe path in release archive: ' + name)
    return path


def validate_manifest(manifest):
    if not isinstance(manifest, dict) or manifest.get('schema') != 1 or manifest.get('repository') != REPOSITORY:
        raise UpdateError('Unrecognized AISAD release manifest')
    semver(manifest.get('version'))
    files = manifest.get('files')
    if not isinstance(files, dict) or not REQUIRED_FILES <= set(files):
        raise UpdateError('Release manifest is missing required files')
    for name, checksum in files.items():
        safe_path(name)
        if name == 'manifest.json' or not isinstance(checksum, str) or not re.fullmatch(r'[0-9a-f]{64}', checksum):
            raise UpdateError('Invalid manifest entry: ' + name)
    return manifest


def unpack_archive(data):
    files = {}
    names = set()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        total = 0
        if len(archive.infolist()) > 100:
            raise UpdateError('Too many files in the release archive')
        for info in archive.infolist():
            path = safe_path(info.filename)
            if path.parts[0] != 'aisad' or len(path.parts) < 2 or info.is_dir():
                raise UpdateError('Unexpected skill archive layout')
            if stat.S_ISLNK(info.external_attr >> 16):
                raise UpdateError('Release archive contains a symlink')
            name = str(PurePosixPath(*path.parts[1:]))
            total += info.file_size
            if total > MAX_DOWNLOAD or name.casefold() in names:
                raise UpdateError('Oversized or duplicate release entry')
            names.add(name.casefold())
            files[name] = archive.read(info)
    manifest = validate_manifest(json.loads(files.get('manifest.json', b'{}')))
    if set(files) != set(manifest['files']) | {'manifest.json'}:
        raise UpdateError('Release archive and manifest disagree')
    if any(digest(files[name]) != value for name, value in manifest['files'].items()):
        raise UpdateError('Release file checksum mismatch')
    try:
        tree = ast.parse(files['runtime/agent_usage.py'].decode('utf-8'))
    except SyntaxError as error:
        raise UpdateError('Invalid collector source') from error
    versions = [ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == 'VERSION' for target in node.targets)]
    if versions != [manifest['version']]:
        raise UpdateError('Collector version does not match the release')
    return manifest, files


def download_release(release):
    base = RELEASES + release['tag'] + '/'
    manifest, files = checked_archive(fetch(base + release['archive']), fetch(base + 'SHA256SUMS', 65536), release['archive'])
    if manifest['version'] != release['version']:
        raise UpdateError('Downloaded version does not match the release tag')
    return manifest, files


def local_files(root):
    found = set()
    for path in root.rglob('*'):
        if path.is_symlink():
            raise UpdateError('Local symlink preserved: ' + str(path.relative_to(root)))
        if path.is_file() and '__pycache__' not in path.parts:
            found.add(path.relative_to(root).as_posix())
    return found


def verify_replaceable(root, incoming):
    if root.is_symlink():
        raise UpdateError('Refusing to replace a symlinked skill directory')
    if not root.exists():
        return
    if not root.is_dir():
        raise UpdateError('Skill destination is not a directory')
    installed = read_json(root / 'manifest.json')
    if installed:
        validate_manifest(installed)
        expected = installed['files']
        allowed = set(expected) | {'manifest.json'}
    else:
        # Adopt a clean copy installed from the same release's GitHub skill path.
        expected = {name: digest(incoming[name]) for name in BOOTSTRAP_FILES}
        allowed = set(expected)
    found = local_files(root)
    modified = sorted(found - allowed)
    modified += [name for name, checksum in expected.items()
                 if name not in found or digest((root / name).read_bytes()) != checksum]
    if modified:
        raise UpdateError('Local modifications preserved: ' + ', '.join(sorted(set(modified))))


@contextmanager
def update_lock(root):
    root.parent.mkdir(parents=True, exist_ok=True)
    with (root.parent / ('.' + root.name + '.update.lock')).open('a+b') as lock:
        lock.seek(0)
        if os.name == 'nt':
            import msvcrt
            if not lock.read(1):
                lock.write(b'0'); lock.flush()
            lock.seek(0)
            try:
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as error:
                raise UpdateError('Another AISAD update is running') from error
            try:
                yield
            finally:
                lock.seek(0); msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                raise UpdateError('Another AISAD update is running') from error
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)


def install_files(root, manifest, files):
    with update_lock(root):
        verify_replaceable(root, files)
        current = read_json(root / 'manifest.json').get('version')
        if current and semver(current) > semver(manifest['version']):
            raise UpdateError('A newer version is installed; automatic downgrades are disabled')
        stage = Path(tempfile.mkdtemp(prefix='.' + root.name + '.stage-', dir=root.parent))
        backup = root.parent / ('.' + root.name + '.previous-' + uuid.uuid4().hex)
        moved = False
        try:
            for name, payload in files.items():
                destination = stage / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(payload)
            if root.exists():
                root.rename(backup); moved = True
            try:
                stage.rename(root)
            except BaseException:
                if moved:
                    backup.rename(root)
                raise
        finally:
            if stage.exists():
                shutil.rmtree(stage)
        if backup.exists():
            try:
                shutil.rmtree(backup)
            except OSError:
                print('Updated successfully; previous code retained at ' + str(backup), file=sys.stderr)
    return manifest['version']


def data_directory(value=None):
    return Path(value or os.environ.get('AISAD_DATA_DIR') or Path.home() / '.local/share/aisad').expanduser().resolve()


def state_path(root, data):
    return data / ('update-' + digest(str(root).encode())[:12] + '.json')


def check_update(root, data):
    installed = read_json(root / 'manifest.json').get('version')
    release = release_info()
    result = dict(installed=installed, latest=release['version'],
                  available=not installed or semver(release['version']) > semver(installed),
                  checked_at=time.time())
    atomic_json(state_path(root, data), result)
    return result, release


def update(root, data, automatic=False):
    state = state_path(root, data)
    previous = read_json(state)
    age = time.time() - previous.get('checked_at', 0)
    if automatic and 0 <= age < CHECK_INTERVAL and (root / 'runtime/agent_usage.py').is_file():
        if not previous.get('available') or previous.get('attempted_at', 0) >= previous['checked_at']:
            return False
        # An explicit check can discover an update without installing it. Apply it
        # on the next invocation without making a second metadata request.
        version = previous['latest']
        semver(version)
        result = previous
        release = dict(version=version, tag='v' + version, archive='aisad-skill-v' + version + '.zip')
    else:
        # Throttle failed automatic checks too; explicit check/update always retries.
        atomic_json(state, {'checked_at': time.time()})
        result, release = check_update(root, data)
    print('Installed: ' + (result['installed'] or 'unbundled') + '; latest: ' + result['latest'], file=sys.stderr, flush=True)
    if result['available']:
        atomic_json(state, dict(result, attempted_at=time.time()))
        manifest, files = download_release(release)
        version = install_files(root, manifest, files)
        atomic_json(state, dict(result, installed=version, available=False))
        print('Updated AISAD skill and collector to ' + version, file=sys.stderr, flush=True)
        return True
    return False


def parser():
    cli = argparse.ArgumentParser(description='Local AISAD usage reports, dashboard and skill updates.', allow_abbrev=False)
    commands = cli.add_subparsers(dest='command', required=True)
    install = commands.add_parser('install', help='Install a released skill', allow_abbrev=False)
    install.add_argument('--target', choices=['codex', 'claude', 'both'], default='codex')
    install.add_argument('--dest', help='Custom skills parent directory')
    install.add_argument('--version', help='Published stable version, e.g. 2.3.0')
    install.add_argument('--archive', help='Local release skill ZIP for offline installation')
    install.add_argument('--checksum-file', help='Local SHA256SUMS (required with --archive)')
    for name in ['version', 'check-update', 'update', 'run', 'usage']:
        command = commands.add_parser(name, allow_abbrev=False,
                                      epilog='Collector options are forwarded, e.g. --json --provider claude --days 7.' if name == 'usage' else None)
        command.add_argument('--data-dir', help='Local reports and update-state directory')
        if name in ('run', 'usage'):
            command.add_argument('--offline', action='store_true', help='Skip all update network requests')
    return cli


def main(argv=None):
    cli = parser()
    args, forwarded = cli.parse_known_args(argv)
    if forwarded and args.command not in ('run', 'usage'):
        cli.error('unrecognized arguments: ' + ' '.join(forwarded))
    root = Path(__file__).absolute().parents[1]
    if args.command == 'install':
        if args.archive:
            if not args.checksum_file or args.version:
                raise UpdateError('Use --archive with --checksum-file, without --version')
            archive = Path(args.archive).expanduser()
            manifest, files = checked_archive(archive.read_bytes(), Path(args.checksum_file).expanduser().read_bytes(), archive.name)
        else:
            if args.checksum_file:
                raise UpdateError('--checksum-file requires --archive')
            manifest, files = download_release(release_info(args.version))
        if args.dest and args.target == 'both':
            raise UpdateError('--dest selects one skills directory; omit --target both')
        if args.dest:
            destinations = [Path(args.dest).expanduser().absolute() / 'aisad']
        else:
            destinations = []
            if args.target in ('codex', 'both'):
                destinations.append(Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex').expanduser().absolute() / 'skills/aisad')
            if args.target in ('claude', 'both'):
                destinations.append(Path(os.environ.get('CLAUDE_CONFIG_DIR') or Path.home() / '.claude').expanduser().absolute() / 'skills/aisad')
        for destination in destinations:
            version = install_files(destination, manifest, files)
            print('Installed AISAD ' + version + ' at ' + str(destination))
        return 0
    data = data_directory(args.data_dir)
    if data == root.resolve() or root.resolve() in data.parents:
        raise UpdateError('Choose a data directory outside the installed skill')
    if args.command == 'version':
        print('AISAD ' + (read_json(root / 'manifest.json').get('version') or 'unbundled skill (run update to install the collector)'))
        return 0
    if args.command == 'check-update':
        result, unused = check_update(root, data)
        print(json.dumps(result, indent=2))
        return 0
    if args.command == 'update':
        update(root, data)
        return 0
    if forwarded[:1] == ['--']:
        forwarded = forwarded[1:]
    changed = False
    if not args.offline and os.environ.get('AISAD_AUTO_UPDATE', '1') != '0':
        try:
            changed = update(root, data, automatic=True)
        except (OSError, ValueError, UpdateError, zipfile.BadZipFile) as error:
            print('Update skipped; keeping installed code: ' + str(error), file=sys.stderr)
    if changed:
        # Execute the new helper so changes to launch behavior take effect immediately.
        return subprocess.call([sys.executable, str(root / 'scripts/aisad.py'), args.command, '--offline', '--data-dir', str(data), '--'] + forwarded)
    runtime = root / 'runtime/agent_usage.py'
    if not runtime.is_file():
        raise UpdateError('No installed collector. Run update with network access or install a release ZIP.')
    mode = ['usage'] if args.command == 'usage' else []
    return subprocess.call([sys.executable, str(runtime)] + mode + ['--output', str(data / 'output')] + forwarded)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, UpdateError, zipfile.BadZipFile) as error:
        raise SystemExit('Error: ' + str(error))
