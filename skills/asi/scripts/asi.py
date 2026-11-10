#!/usr/bin/env python3
"""Install, update and run ASI without transmitting usage data. macOS and Linux, Python 3.9+."""
import argparse
import ast
from contextlib import contextmanager
import datetime
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import shlex
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
import zipfile

REPOSITORY = 'aiatsuk/asi'
API = 'https://api.github.com/repos/' + REPOSITORY
RELEASES = 'https://github.com/' + REPOSITORY + '/releases/download/'
CHECK_INTERVAL = 24 * 60 * 60
MAX_DOWNLOAD = 10 * 1024 * 1024
REQUIRED_FILES = {'SKILL.md', 'agents/openai.yaml', 'scripts/asi.py', 'runtime/agent_usage.py'}
BOOTSTRAP_FILES = REQUIRED_FILES - {'runtime/agent_usage.py'}
# Up to 1.5.2 ASI was named AISAD. These names are read only to carry an existing setup over.
LEGACY_NAME = 'aisad'
LEGACY_REPOSITORY = 'aiatsuk/aisad'
LEGACY_CLI_MARKER = '# AISAD CLI launcher'
APP_NAMES = ('ASI.app', 'ASIMenuBar.app', 'AISAD.app', 'AISADMenuBar.app')
BUNDLE_IDS = ('com.aiatsuk.asi.menubar', 'com.aiatsuk.aisad.menubar')


class UpdateError(Exception):
    pass


def setting(name, default=None):
    """ASI_<name>, else the 1.x AISAD_<name>; an empty value counts as unset."""
    for key in ('ASI_' + name, 'AISAD_' + name):
        value = os.environ.get(key)
        if value:
            return value
    return default


def semver(value):
    match = re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', str(value))
    if not match:
        raise UpdateError('Expected a stable version such as 1.0.0')
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
    request = urllib.request.Request(url, headers={'User-Agent': 'ASI-skill', 'Accept': 'application/json'})
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
    name = 'asi-skill-v' + candidate + '.zip'
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
        raise UpdateError('Unrecognized ASI release manifest')
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
            if path.parts[0] != 'asi' or len(path.parts) < 2 or info.is_dir():
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
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise UpdateError('Another ASI update is running') from error
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def install_files(root, manifest, files, allow_downgrade=False):
    with update_lock(root):
        verify_replaceable(root, files)
        current = read_json(root / 'manifest.json').get('version')
        if current and semver(current) > semver(manifest['version']) and not allow_downgrade:
            raise UpdateError('A newer version is installed; use install --allow-downgrade for an intentional version reset')
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


def legacy_install_problem(root):
    """None when a 1.x skill directory is an unmodified release install, else why it is kept."""
    if root.is_symlink() or not root.is_dir():
        return 'not a plain directory'
    manifest = read_json(root / 'manifest.json')
    files = manifest.get('files')
    if manifest.get('schema') != 1 or manifest.get('repository') != LEGACY_REPOSITORY or not isinstance(files, dict):
        return 'no AISAD release manifest'
    # Names are compared with the files actually present before any is read.
    if local_files(root) != set(files) | {'manifest.json'}:
        return 'local changes'
    if any(not isinstance(checksum, str) or digest((root / name).read_bytes()) != checksum for name, checksum in files.items()):
        return 'local changes'
    return None


def remove_legacy_install(destination):
    """Remove the 1.x skill installed next to a new one when it verifies; keep anything else."""
    old = destination.parent / LEGACY_NAME
    if not old.exists() and not old.is_symlink():
        return
    try:
        # The 1.x updater takes the same lock, so an update in flight is never cut short.
        with update_lock(old):
            problem = legacy_install_problem(old)
            if problem is None:
                # Rename first, so the skill disappears at once even if deleting it fails halfway.
                trash = old.parent / ('.' + old.name + '.removed-' + uuid.uuid4().hex)
                old.rename(trash)
                print('Removed the previous AISAD skill at ' + str(old))
                try:
                    shutil.rmtree(trash)
                except OSError as error:
                    print('Could not delete its files at ' + str(trash) + ': ' + str(error), file=sys.stderr)
                return
    except (OSError, UpdateError) as error:
        problem = str(error)
    print('Kept the previous AISAD skill at ' + str(old) + ' (' + problem + '); remove it yourself when no longer needed', file=sys.stderr)


def alias_legacy_cli(cli_path):
    """Make a 1.x `aisad` command written by this installer run the new `asi` command."""
    old = cli_path.parent / LEGACY_NAME
    if old.is_symlink() or not old.is_file():
        return
    try:
        text = old.read_text()
    except (OSError, ValueError):
        return
    if text.splitlines()[1:2] != [LEGACY_CLI_MARKER]:
        return  # Not ours: an unrelated command is left alone.
    body = '#!/bin/sh\n' + LEGACY_CLI_MARKER + '\n# Alias for the asi command\nexec ' + shlex.quote(str(cli_path)) + ' "$@"\n'
    try:
        if text != body:
            old.write_text(body)
        old.chmod(0o755)
    except OSError as error:
        print('Could not point ' + str(old) + ' at ' + str(cli_path) + ': ' + str(error), file=sys.stderr)
        return
    print('The aisad command at ' + str(old) + ' now runs ' + str(cli_path))


def data_directory(value=None):
    chosen = value or setting('DATA_DIR')
    return Path(chosen).expanduser().resolve() if chosen else default_data_directory()


def default_data_directory(home=None):
    """~/.local/share/asi; a 1.x ~/.local/share/aisad moves there once.

    A failed move keeps the old directory in use, so reports, budget and update
    state stay where they are until the move can succeed."""
    share = (home or Path.home()) / '.local/share'
    new, old = share / 'asi', share / LEGACY_NAME
    if not new.exists() and not new.is_symlink() and old.is_dir():
        try:
            old.rename(new)
            print('Moved local data from ' + str(old) + ' to ' + str(new), file=sys.stderr)
        except OSError as error:
            if not new.is_dir():
                # Another launcher may have moved it first; otherwise keep the old place.
                print('Keeping local data in ' + str(old) + '; could not move it to ' + str(new) + ': ' + str(error), file=sys.stderr)
                return old.resolve()
    return new.resolve()


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
    installed = read_json(root / 'manifest.json').get('version')
    age = time.time() - previous.get('checked_at', 0)
    if automatic and previous.get('installed') == installed and 0 <= age < CHECK_INTERVAL and (root / 'runtime/agent_usage.py').is_file():
        if not previous.get('available') or previous.get('attempted_at', 0) >= previous['checked_at']:
            return False
        # An explicit check can discover an update without installing it. Apply it
        # on the next invocation without making a second metadata request.
        version = previous['latest']
        semver(version)
        result = previous
        release = dict(version=version, tag='v' + version, archive='asi-skill-v' + version + '.zip')
    else:
        # Throttle failed automatic checks too; explicit check/update always retries.
        # A reinstall can change the version outside this updater. Never reuse a
        # pending release or a failed check from that previous installation.
        atomic_json(state, {'checked_at': time.time(), 'installed': installed})
        result, release = check_update(root, data)
    print('Installed: ' + (result['installed'] or 'unbundled') + '; latest: ' + result['latest'], file=sys.stderr, flush=True)
    if result['available']:
        atomic_json(state, dict(result, attempted_at=time.time()))
        manifest, files = download_release(release)
        version = install_files(root, manifest, files)
        atomic_json(state, dict(result, installed=version, available=False))
        print('Updated ASI skill and collector to ' + version, file=sys.stderr, flush=True)
        return True
    return False


def parser():
    cli = argparse.ArgumentParser(description='Local ASI usage reports, dashboard and skill updates.', allow_abbrev=False)
    commands = cli.add_subparsers(dest='command', required=True)
    install = commands.add_parser('install', help='Install a released skill', allow_abbrev=False)
    install.add_argument('--cli-dir', help='Also install an asi terminal command in this directory; no shell settings are changed')
    install.add_argument('--target', choices=['codex', 'claude', 'both'], default='codex')
    install.add_argument('--dest', help='Custom skills parent directory')
    install.add_argument('--version', help='Published stable version, e.g. 1.0.0')
    install.add_argument('--allow-downgrade', action='store_true', help='Allow an intentional reinstall to a lower version; preserves local edits and data')
    install.add_argument('--archive', help='Local release skill ZIP for offline installation')
    install.add_argument('--checksum-file', help='Local SHA256SUMS (required with --archive)')
    maintain = commands.add_parser('maintain', allow_abbrev=False, help='Run the daily update check and price refresh now (launches do this in the background)')
    maintain.add_argument('--data-dir', help='Local reports and update-state directory')
    maintain.add_argument('tasks', nargs='*', metavar='{update,prices}', help='Default: both')
    for name in ['version', 'check-update', 'update', 'run', 'usage', 'analyze', 'statusline', 'collect', 'sessions', 'session', 'prices', 'chart', 'budget', 'forecast', 'menubar']:
        command = commands.add_parser(name, allow_abbrev=False,
                                      help='Open the macOS menu bar app; add --json for its report' if name == 'menubar' else None,
                                      epilog='Collector options are forwarded, e.g. --json --provider claude --days 7. Use -- --help for all collector options.' if name in ('usage', 'analyze', 'statusline', 'run', 'collect', 'sessions', 'session', 'prices', 'chart', 'budget', 'menubar') else None)
        command.add_argument('--data-dir', help='Local reports and update-state directory')
        if name in ('run', 'usage', 'analyze', 'statusline', 'collect', 'sessions', 'session', 'prices', 'chart', 'budget', 'forecast', 'menubar'):
            command.add_argument('--offline', action='store_true', help='Skip all update network requests')
    return cli


def update_due(root, data):
    """Whether update(automatic=True) would reach the network now (same throttle)."""
    previous = read_json(state_path(root, data))
    installed = read_json(root / 'manifest.json').get('version')
    age = time.time() - previous.get('checked_at', 0)
    if previous.get('installed') == installed and 0 <= age < CHECK_INTERVAL and (root / 'runtime/agent_usage.py').is_file():
        return bool(previous.get('available')) and previous.get('attempted_at', 0) < previous['checked_at']
    return True


def prices_due(data):
    checked = read_json(data / 'output/prices-models-dev.meta.json').get('checked_at')
    if checked:
        try:
            age = time.time() - datetime.datetime.fromisoformat(checked).timestamp()
            return not 0 <= age < CHECK_INTERVAL
        except ValueError:
            pass
    return True


def refresh_prices(runtime, data):
    """Read published rates; a failed refresh keeps the rates already stored locally.

    The collector itself stays offline; this launcher owns the one throttled
    network moment per day, so the price refresh rides along with it.
    """
    try:
        subprocess.run([sys.executable, str(runtime), 'prices', '--refresh', '--json', '--output', str(data / 'output')],
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=60, check=True)
    except (OSError, subprocess.SubprocessError) as error:
        print('Price refresh skipped; keeping stored rates: ' + str(error), file=sys.stderr)


def maintenance_tasks(root, data, command, offline):
    if offline:
        return []
    tasks = []
    if command != 'budget' and setting('AUTO_UPDATE', '1') != '0' and update_due(root, data):
        tasks.append('update')
    if command not in ('prices', 'budget') and setting('AUTO_PRICES', '1') != '0' and prices_due(data):
        tasks.append('prices')
    return tasks


def start_maintenance(root, data, tasks):
    """Run the daily network work in a detached helper; a report never waits on it.

    An update found here applies from the next launch: the running report keeps
    the code it started with. Output goes to a log, never into a terminal view.
    """
    data.mkdir(parents=True, exist_ok=True)
    try:
        with (data / 'maintenance.log').open('ab') as log:
            subprocess.Popen([sys.executable, str(root / 'scripts/asi.py'), 'maintain', '--data-dir', str(data)] + tasks,
                             stdin=subprocess.DEVNULL, stdout=log, stderr=log, close_fds=True, start_new_session=True)
    except OSError as error:
        print('Background update check skipped: ' + str(error), file=sys.stderr)


def maintain(root, data, tasks):
    print(datetime.datetime.now().isoformat(timespec='seconds') + ' maintain ' + ' '.join(tasks), file=sys.stderr, flush=True)
    if 'update' in tasks:
        try:
            update(root, data, automatic=True)
        except (OSError, ValueError, UpdateError, zipfile.BadZipFile) as error:
            print('Update skipped; keeping installed code: ' + str(error), file=sys.stderr)
    runtime = root / 'runtime/agent_usage.py'
    if 'prices' in tasks and runtime.is_file() and prices_due(data):
        refresh_prices(runtime, data)


def launch_menubar():
    """Open the installed companion without collecting usage or updating the CLI."""
    if sys.platform != 'darwin':
        raise UpdateError('The ASI menu bar app requires macOS. Use menubar --json for its report.')
    # New names first in both folders, then the 1.x AISAD names.
    candidates = [directory / name for name in APP_NAMES
                  for directory in (Path.home() / 'Applications', Path('/Applications'))]
    app = next((path for path in candidates if path.is_dir()), None)
    commands = [['/usr/bin/open', str(app)]] if app else [['/usr/bin/open', '-b', bundle] for bundle in BUNDLE_IDS]
    # Only the last attempt may print open's own error; an earlier miss just falls through.
    if not any(subprocess.call(command, **({} if command is commands[-1] else {'stderr': subprocess.DEVNULL})) == 0
               for command in commands):
        raise UpdateError('Could not open the ASI menu bar app. Install ASI.app in ~/Applications or /Applications, '
                          'or build it from the repository with ./script/build_and_run.sh.')
    return 0


def main(argv=None):
    cli = parser()
    args, forwarded = cli.parse_known_args(argv)
    if forwarded and args.command not in ('run', 'usage', 'analyze', 'statusline', 'collect', 'sessions', 'session', 'prices', 'chart', 'budget', 'forecast', 'menubar'):
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
            destinations = [Path(args.dest).expanduser().absolute() / 'asi']
        else:
            destinations = []
            if args.target in ('codex', 'both'):
                destinations.append(Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex').expanduser().absolute() / 'skills/asi')
            if args.target in ('claude', 'both'):
                destinations.append(Path(os.environ.get('CLAUDE_CONFIG_DIR') or Path.home() / '.claude').expanduser().absolute() / 'skills/asi')
        cli_path = None
        if args.cli_dir:
            cli_path = Path(args.cli_dir).expanduser().absolute() / 'asi'
            cli_body = '#!/bin/sh\n# ASI CLI launcher\nexec python3 ' + shlex.quote(str(destinations[0] / 'scripts/asi.py')) + ' "$@"\n'
            if cli_path.is_symlink() or (cli_path.exists() and cli_path.read_text() != cli_body):
                raise UpdateError('Existing terminal command preserved: ' + str(cli_path))
        for destination in destinations:
            version = install_files(destination, manifest, files, allow_downgrade=args.allow_downgrade)
            print('Installed ASI ' + version + ' at ' + str(destination))
            remove_legacy_install(destination)
        if cli_path is not None:
            cli_path.parent.mkdir(parents=True, exist_ok=True)
            cli_path.write_text(cli_body)
            cli_path.chmod(0o755)
            print('Installed terminal command at ' + str(cli_path))
            alias_legacy_cli(cli_path)
        return 0
    if forwarded[:1] == ['--']:
        forwarded = forwarded[1:]
    if args.command == 'menubar' and not forwarded:
        return launch_menubar()
    data = data_directory(args.data_dir)
    if data == root.resolve() or root.resolve() in data.parents:
        raise UpdateError('Choose a data directory outside the installed skill')
    if args.command == 'version':
        print('ASI ' + (read_json(root / 'manifest.json').get('version') or 'unbundled skill (run update to install the collector)'))
        return 0
    if args.command == 'check-update':
        result, unused = check_update(root, data)
        print(json.dumps(result, indent=2))
        return 0
    if args.command == 'update':
        update(root, data)
        return 0
    if args.command == 'maintain':
        if set(args.tasks) - {'update', 'prices'}:
            cli.error('maintain tasks are update and prices')
        maintain(root, data, args.tasks or ['update', 'prices'])
        return 0
    runtime = root / 'runtime/agent_usage.py'
    tasks = maintenance_tasks(root, data, args.command, args.offline)
    if not runtime.is_file() and 'update' in tasks:
        # Nothing to run yet: the first install has to finish before the report.
        try:
            update(root, data, automatic=True)
        except (OSError, ValueError, UpdateError, zipfile.BadZipFile) as error:
            print('Update skipped; keeping installed code: ' + str(error), file=sys.stderr)
        tasks.remove('update')
    if not runtime.is_file():
        raise UpdateError('No installed collector. Run update with network access or install a release ZIP.')
    if tasks:
        start_maintenance(root, data, tasks)
    mode = [args.command] if args.command in ('usage', 'analyze', 'statusline', 'collect', 'sessions', 'session', 'prices', 'chart', 'budget', 'forecast', 'menubar') else []
    return subprocess.call([sys.executable, str(runtime)] + mode + ['--output', str(data / 'output')] + forwarded)

if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, UpdateError, zipfile.BadZipFile) as error:
        raise SystemExit('Error: ' + str(error))
