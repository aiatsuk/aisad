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
# Claude Code skills shipped inside this one and linked next to it on install.
SUBSKILLS = ('asi-analyze', 'asi-autopilot', 'asi-suggest', 'asi-ultraanalyze')
SUBSKILL_FILE = re.compile(r'subskills/([a-z0-9][a-z0-9-]*)/SKILL\.md')
REQUIRED_FILES = {'SKILL.md', 'agents/openai.yaml', 'scripts/asi.py', 'runtime/agent_usage.py'} | {
    'subskills/' + name + '/SKILL.md' for name in SUBSKILLS}
BOOTSTRAP_FILES = REQUIRED_FILES - {'runtime/agent_usage.py'}
# Reports the launcher forwards to the collector as the collector's command of the same name.
COLLECTOR_COMMANDS = ('usage', 'analyze', 'statusline', 'collect', 'sessions', 'session', 'prices', 'chart',
                      'budget', 'forecast', 'menubar', 'dashboard', 'fit', 'suggest')
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


def validate_manifest(manifest, required=REQUIRED_FILES):
    if not isinstance(manifest, dict) or manifest.get('schema') != 1 or manifest.get('repository') != REPOSITORY:
        raise UpdateError('Unrecognized ASI release manifest')
    semver(manifest.get('version'))
    files = manifest.get('files')
    if not isinstance(files, dict) or not required <= set(files):
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
        # An installed release may predate files required now (the sub-skills came in 2.0.0).
        # Its manifest only has to be well formed: it lists the files that may be replaced.
        validate_manifest(installed, required=set())
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
                # Its update lock has nothing left to guard. Unlinking it while held is safe.
                try:
                    (old.parent / ('.' + old.name + '.update.lock')).unlink()
                except OSError:
                    pass
                try:
                    shutil.rmtree(trash)
                except OSError as error:
                    print('Could not delete its files at ' + str(trash) + ': ' + str(error), file=sys.stderr)
                return
    except (OSError, UpdateError) as error:
        problem = str(error)
    print('Kept the previous AISAD skill at ' + str(old) + ' (' + problem + '); remove it yourself when no longer needed', file=sys.stderr)


def written_by_installer(text):
    """Whether an `aisad` command holds exactly what an installer wrote: the 1.x launcher
    (`exec python3 <skills>/aisad/scripts/aisad.py "$@"`, the only shape 1.x wrote) or the
    alias below. Any edit makes it the user's own."""
    for pattern, ending in ((r'exec python3 (.+) "\$@"', '/aisad/scripts/aisad.py'),
                            (r'# Alias for the asi command\nexec (.+) "\$@"', '/asi')):
        match = re.fullmatch('#!/bin/sh\n' + re.escape(LEGACY_CLI_MARKER) + '\n' + pattern + '\n', text)
        if not match:
            continue
        try:
            words = shlex.split(match[1])
        except ValueError:
            return False
        return (len(words) == 1 and shlex.quote(words[0]) == match[1] and words[0].startswith('/')
                and words[0].endswith(ending))
    return False


def alias_legacy_cli(cli_path):
    """Make a 1.x `aisad` command written by this installer run the new `asi` command."""
    old = cli_path.parent / LEGACY_NAME
    if old.is_symlink() or not old.is_file():
        return
    try:
        with open(str(old), encoding='utf-8', newline='') as handle:
            text = handle.read()  # as written: line endings are part of what the installer wrote
    except (OSError, ValueError):
        return
    if text.splitlines()[1:2] != [LEGACY_CLI_MARKER]:
        return  # Not ours: an unrelated command is left alone.
    if not written_by_installer(text):
        print('Left the aisad command at ' + str(old) + ' as it is: it was changed after the AISAD installer wrote it', file=sys.stderr)
        return
    body = '#!/bin/sh\n' + LEGACY_CLI_MARKER + '\n# Alias for the asi command\nexec ' + shlex.quote(str(cli_path)) + ' "$@"\n'
    try:
        if text != body:
            old.write_text(body)
        old.chmod(0o755)
    except OSError as error:
        print('Could not point ' + str(old) + ' at ' + str(cli_path) + ': ' + str(error), file=sys.stderr)
        return
    print('The aisad command at ' + str(old) + ' now runs ' + str(cli_path))


def claude_directory():
    return Path(os.environ.get('CLAUDE_CONFIG_DIR') or Path.home() / '.claude').expanduser().absolute()


def step_out(path, depth=0):
    """An absolute path with each '..' applied as the system applies it, following only the
    links a '..' has to leave. Every other link stays a link in the result."""
    if depth > 40:
        raise OSError('Too many levels of symbolic links: ' + str(path))
    current = Path(path.parts[0])
    for part in path.parts[1:]:
        if part != '..':
            current = current / part
            continue
        # '..' leaves where a link points, not the folder that holds the link.
        while current.is_symlink():
            depth += 1
            current = step_out(Path(os.path.join(str(current.parent), os.readlink(str(current)))), depth)
        current = current.parent
    return current


def skill_root(script=None):
    """The installed skill directory of this launcher.

    A sub-skill runs it through its own link, as skills/asi-suggest/../../scripts/asi.py.
    There '..' has to follow that link; nothing else is resolved, so a symlinked skill
    directory is still seen (and refused) by updates on that route too."""
    path = Path(script or __file__).absolute()
    if '..' in path.parts:
        path = step_out(path)
    return path.parents[1]


def subskill_names(root):
    """Sub-skills of the installed release, read from its manifest."""
    files = read_json(root / 'manifest.json').get('files')
    if not isinstance(files, dict):
        return []
    found = (SUBSKILL_FILE.fullmatch(name) for name in files)
    return sorted({match[1] for match in found if match and match[1] != root.name})


def link_target(path):
    """Where a symlink points, as an absolute path, without following further links."""
    return Path(os.path.normpath(os.path.join(str(path.parent), os.readlink(str(path)))))


def link_subskills(root):
    """Link each sub-skill next to the skill for Claude Code: skills/<name> -> asi/subskills/<name>.

    A missing link is created and a correct one left alone. Anything else at that path is
    kept as it is, with one line, unless it is a link into asi/subskills/. A link of ours to a
    sub-skill the release no longer has is removed. Returns how many paths were kept."""
    home = Path(os.path.normpath(str(root / 'subskills')))
    names = subskill_names(root)
    kept, made = 0, []
    for name in names:
        link = root.parent / name
        temporary = None
        try:
            if link.is_symlink():
                target = link_target(link)
                if target == home / name:
                    continue
                if target.parent != home:
                    raise FileExistsError
                # Ours, but pointing at another sub-skill: replace it in one step.
                temporary = root.parent / ('.' + name + '.link-' + uuid.uuid4().hex)
                os.symlink(root.name + '/subskills/' + name, str(temporary))
                os.replace(str(temporary), str(link))
                temporary = None
            elif link.exists():
                raise FileExistsError
            else:
                os.symlink(root.name + '/subskills/' + name, str(link))
            made.append(name)
        except FileExistsError:
            kept += 1
            print('Kept ' + str(link) + ': it is not a link into ' + root.name + '/subskills/; move it away and install again to get /' + name, file=sys.stderr)
        except OSError as error:
            kept += 1
            print('Could not link ' + str(link) + ': ' + str(error), file=sys.stderr)
        finally:
            if temporary is not None and temporary.is_symlink():
                temporary.unlink()
    try:
        siblings = sorted(root.parent.iterdir())
    except OSError:
        siblings = []
    for link in siblings:
        try:
            if link.name not in names and link.is_symlink() and not link.exists() and link_target(link).parent == home:
                link.unlink()
                print('Removed ' + str(link) + ': this release no longer has that sub-skill')
        except OSError:
            pass
    if made:
        print('Linked Claude Code skills ' + ', '.join('/' + name for name in made) + ' in ' + str(root.parent))
    return kept


def links_wanted(root):
    """Whether an update keeps sub-skill links next to this skill: it is the Claude Code
    skill, or a link of ours is already there (an install with --dest and --target claude)."""
    try:
        if root.parent.resolve() == (claude_directory() / 'skills').resolve():
            return True
        home = Path(os.path.normpath(str(root / 'subskills')))
        return any(path.is_symlink() and link_target(path).parent == home for path in root.parent.iterdir())
    except OSError:
        return False


# Model rules: one marked block in Claude Code's CLAUDE.md, and the autopilot switch.
# ASI installs no hooks. The first-message hint and the autopilot are plain instructions in
# that block; this is its only writer, and text outside the markers is never changed.
RULES_BEGIN = '<!-- asi:begin -->'
RULES_END = '<!-- asi:end -->'
# The AIR prototype kept the same rules between these markers; the first write takes them over.
AIR_BEGIN = '<!-- air:begin -->'
AIR_END = '<!-- air:end -->'
DEFAULT_RULES = {'hint': False, 'autopilot': False}  # both are opt-in and independent

HINT = """\
# ASI: model and effort

Managed by `asi rules`; edits inside this block are not kept.

Only in a main interactive session (never as a subagent, workflow agent or headless run): start your reply to the first user message with a short ASI note of two or three lines: the task class, the model, effort and modes the guide below suggests, one line of why, and whether the current model already fits. Then do the task without waiting for an answer. Skip the note for trivial prompts (greetings, yes/no, slash commands), for a prompt written by a script or harness, and whenever the reply must follow a fixed output format. Do not repeat it later; `/asi-suggest` gives the full version on request.

Guide (start, then raise if it falls short):
- everyday engineering, debugging, multi-PR work, computer use, unsure: Opus, medium then high
- well-scoped coding, documents, review, drafting, investigation: Sonnet, medium (high for harder scoped work); chat: Sonnet, low
- classification, extraction, and subagents that search, read logs or summarize: Haiku
- major refactor or migration, architecture, leading many subagents, deep research, long unattended runs: Fable, medium then high
- change effort before model; past high, try the next model up at a lower effort
- a model switch re-writes the whole cache: switch at the start, after /compact, or in a new session
"""

AUTOPILOT = """\
## ASI autopilot: on

For every subagent you spawn (Agent tool) and every agent call in a Workflow script, choose the model and effort for that piece of work and pass them explicitly. A model or effort already named by the agent definition, a skill, the workflow, repo routing or the user wins; fill in only where nothing is named.
- search, reading, listing, fetching, log digging, summaries, relay or bookkeeping steps: haiku, no effort passed
- well-scoped coding from a clear spec, review, drafting, investigation: sonnet, medium (high for the harder ones)
- multi-file implementation, debugging with an unknown cause, computer use or screenshots: opus, medium (high if it falls short)
- architecture or migration plans, a lead that coordinates many agents, deep research: fable, medium (high if it falls short)

When a piece fails: add a self-check, then raise effort one step, then go one model up at a lower effort. Where a result can be checked automatically, run it at low and re-run only the failures at high. Say each choice in a few words when you make it ("search: haiku").

Never change the main session's own model or effort: a switch re-writes the whole cache. When the main thread's work has clearly moved to another class, say so in one line and suggest switching after /compact or in a new session.
"""


class RulesError(Exception):
    pass


def claude_md():
    return claude_directory() / 'CLAUDE.md'


def rules_state_path(data):
    return data / 'model-rules.json'


def load_rules(data):
    """The saved switches; a missing or malformed state file means the defaults."""
    saved = read_json(rules_state_path(data))
    return {key: bool(saved.get(key, value)) for key, value in DEFAULT_RULES.items()}


def save_rules(data, state):
    atomic_json(rules_state_path(data), state)


def write_text_atomically(path, text):
    """Replace a file's text in one step, keeping its mode (0644 when new); newlines as given."""
    fd, temporary = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + '.', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as output:
            output.write(text)
        os.chmod(temporary, (path.stat().st_mode & 0o777) if path.exists() else 0o644)
        os.replace(temporary, str(path))
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def rules_block(state):
    """The managed block for a state; empty when nothing is switched on."""
    parts = []
    if state['hint']:
        parts.append(HINT)
    if state['autopilot']:
        parts.append(AUTOPILOT if state['hint'] else AUTOPILOT.replace('## ASI', '# ASI', 1))
    if not parts:
        return ''
    return RULES_BEGIN + '\n' + '\n'.join(parts).rstrip() + '\n' + RULES_END + '\n'


MARKER = re.compile(r'<!-- (?:asi|air):(?:begin|end) -->')
# A line that holds markers and nothing else, spaces and tabs aside.
MARKER_LINE = re.compile(r'^[ \t]*(?:<!-- (?:asi|air):(?:begin|end) -->[ \t]*)+(?=\r?\n|\Z)', re.M)


def marker_lines(text):
    """Every ASI and AIR marker that stands alone on its line: {marker: [(line start, line end)]}.

    Marker text with other text on its line (prose, a backticked mention) is ordinary text.
    A line of nothing but two or more markers is neither, so it is refused."""
    found = {marker: [] for marker in (RULES_BEGIN, RULES_END, AIR_BEGIN, AIR_END)}
    for match in MARKER_LINE.finditer(text):
        markers = MARKER.findall(match.group())
        if len(markers) > 1:
            raise RulesError('one line holds the markers %s; fix the file by hand first' % ' '.join(markers))
        found[markers[0]].append((match.start(), match.end()))
    return found


def marked_block(found, begin, end, origin=''):
    """The (start, stop) of the one block between these marker lines, None when there is none."""
    starts, stops = found[begin], found[end]
    if len(starts) != len(stops) or len(starts) > 1:
        raise RulesError("found %d '%s' and %d '%s' markers%s; fix the file by hand first" % (len(starts), begin, len(stops), end, origin))
    if not starts:
        return None
    if stops[0][0] < starts[0][0]:
        raise RulesError('the end marker comes before the begin marker%s; fix the file by hand first' % origin)
    return starts[0][0], stops[0][1]


def replace_block(text, span, new, nl):
    head, tail = text[:span[0]], text[span[1]:]
    if tail.startswith(nl):
        tail = tail[len(nl):]
    if not new:
        head, tail = head.rstrip('\r\n'), tail.lstrip('\r\n')
        if head and tail:
            return head + nl + nl + tail
        return head + nl if head else tail
    return head + new + tail


def render_rules(text, state):
    """Return CLAUDE.md text with the managed block replaced, added or removed.

    Text outside the markers is kept byte for byte, apart from the blank lines that separate
    it from the block. The file's own line ending (LF or CRLF) is used. A block left by the
    AIR prototype is replaced in place, or dropped when an ASI block exists as well. A marker
    counts only alone on its line; marker text inside other lines is kept as it is."""
    found = marker_lines(text)
    ours = marked_block(found, RULES_BEGIN, RULES_END)
    air = marked_block(found, AIR_BEGIN, AIR_END, ' (left by the earlier AIR tool)')
    if ours and air and ours[0] < air[1] and air[0] < ours[1]:
        raise RulesError('the ASI and AIR blocks overlap; fix the file by hand first')
    nl = '\r\n' if '\r\n' in text else '\n'
    new = rules_block(state).replace('\n', nl)
    if air:
        if not ours:
            return replace_block(text, air, new, nl)
        text = replace_block(text, air, '', nl)
        ours = marked_block(marker_lines(text), RULES_BEGIN, RULES_END)
    if ours:
        return replace_block(text, ours, new, nl)
    if not new:
        return text
    if not text.strip():
        return new
    return text.rstrip('\r\n') + nl + nl + new


def apply_rules(state):
    """Write the block for a state. Returns (path, changed). A symlinked CLAUDE.md is followed,
    so the link stays a link; a file that is not UTF-8 is refused untouched."""
    path = claude_md()
    # realpath, unlike Path.resolve on Python 3.9, does not raise on a link loop; it stops at a
    # link instead, which is refused rather than replaced by a plain file.
    target = Path(os.path.realpath(str(path))) if path.is_symlink() else path
    if target.is_symlink():
        raise RulesError('the link loops; fix it by hand first')
    old = ''
    if target.exists():
        try:
            with open(str(target), encoding='utf-8', newline='') as handle:
                old = handle.read()
        except UnicodeDecodeError as error:
            raise RulesError('not valid UTF-8 (%s at byte %d); left untouched' % (error.reason, error.start)) from error
    new = render_rules(old, state)
    if new == old:
        return path, False
    # The new text replaces the file through a rename, which a read-only mode would not stop.
    if target.exists() and not os.access(str(target), os.W_OK):
        raise RulesError('the file is not writable (mode %04o); left untouched' % (target.stat().st_mode & 0o7777))
    target.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomically(target, new)
    return path, True


def rules_on_disk():
    """({'hint': bool, 'autopilot': bool} for the block in CLAUDE.md, None), or (None, why the file
    could not be read). A missing file has no block."""
    try:
        with open(str(claude_md()), encoding='utf-8', newline='') as handle:
            text = handle.read()
    except FileNotFoundError:
        return dict.fromkeys(DEFAULT_RULES, False), None
    except UnicodeDecodeError:
        return None, 'not valid UTF-8'
    except OSError as error:
        return None, error.strerror or str(error)
    try:
        block = marked_block(marker_lines(text), RULES_BEGIN, RULES_END)
    except RulesError:
        block = None
    body = text[block[0]:block[1]] if block else ''
    return {'hint': 'ASI: model and effort' in body, 'autopilot': 'ASI autopilot: on' in body}, None


def set_rules(data, state):
    """Save the state and write the block; neither is left changed when the other fails."""
    before = load_rules(data)
    try:
        save_rules(data, state)
    except OSError as error:
        print('Error: cannot save ' + str(rules_state_path(data)) + ': ' + str(error), file=sys.stderr)
        return 1
    try:
        path, changed = apply_rules(state)
    except (RulesError, OSError) as error:
        try:
            save_rules(data, before)
        except OSError:
            pass
        where = str(claude_md()) if isinstance(error, RulesError) else 'cannot write ' + str(claude_md())
        print('Error: ' + where + ': ' + str(error), file=sys.stderr)
        return 1
    print(('Updated ' if changed else 'No change needed in ') + str(path))
    return 0


def rules_command(data, command, mode):
    state = load_rules(data)
    if mode == 'status':
        found, problem = rules_on_disk()
        unreadable = 'the file could not be read (' + str(problem) + ')'
        present = lambda key: 'present' if found[key] else 'absent'
    if command == 'autopilot':
        if mode == 'show':
            print(AUTOPILOT)
            return 0
        if mode == 'status':
            print('autopilot: ' + ('on' if state['autopilot'] else 'off') + ' (rules block in ' + str(claude_md()) + ': '
                  + (present('autopilot') if found else unreadable) + ')')
            return 0
        state['autopilot'] = mode == 'on'
        if set_rules(data, state):
            return 1
        if state['autopilot']:
            print('Autopilot is on for new sessions. Rules to follow in this session from now on:\n')
            print(AUTOPILOT)
        else:
            print("Autopilot is off. From now on in this session, stop choosing models and effort for subagents "
                  "on ASI's behalf; follow agent definitions and the session defaults.")
        return 0
    if mode == 'status':
        print('first-message hint: ' + ('on' if state['hint'] else 'off') + '; autopilot: ' + ('on' if state['autopilot'] else 'off'))
        print('block in ' + str(claude_md()) + ': ' + ('hint ' + present('hint') + ', autopilot ' + present('autopilot') if found else unreadable))
        return 0
    if mode == 'show':
        print(rules_block(state) or '(nothing switched on)')
        return 0
    if mode in ('on', 'off'):
        state['hint'] = mode == 'on'
    return set_rules(data, state)


def data_directory(value=None, move=True):
    chosen = value or setting('DATA_DIR')
    return Path(chosen).expanduser().resolve() if chosen else default_data_directory(move=move)


def default_data_directory(home=None, move=True):
    """~/.local/share/asi; a 1.x ~/.local/share/aisad moves there once.

    The old path stays behind as a link to the new one, so a status line script or a
    1.x app that still reads it keeps working. A failed move keeps the old directory
    in use, so reports, budget and update state stay where they are until the move
    can succeed. With move=False (commands that only read) nothing moves or is created:
    the new directory if it exists, else the old one if it exists, else the new path."""
    share = (home or Path.home()) / '.local/share'
    new, old = share / 'asi', share / LEGACY_NAME
    if not move:
        return old.resolve() if not new.exists() and not new.is_symlink() and old.is_dir() else new.resolve()
    if not new.exists() and not new.is_symlink() and old.is_dir():
        if old.is_symlink():
            return old.resolve()  # Someone pointed the old path elsewhere on purpose.
        try:
            old.rename(new)
            print('Moved local data from ' + str(old) + ' to ' + str(new), file=sys.stderr)
        except OSError as error:
            if not new.is_dir():
                # Another launcher may have moved it first; otherwise keep the old place.
                print('Keeping local data in ' + str(old) + '; could not move it to ' + str(new) + ': ' + str(error), file=sys.stderr)
                return old.resolve()
        else:
            try:
                old.symlink_to(new.name, target_is_directory=True)
            except OSError:
                pass  # The link is a convenience; the data is already in the new place.
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
        try:
            if links_wanted(root):
                # Read from the new manifest, so sub-skills added by this release get links too.
                link_subskills(root)
        except OSError as error:
            print('Updated, but could not link the sub-skills: ' + str(error), file=sys.stderr)
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
    helps = {'menubar': 'Open the macOS menu bar app; add --json for its report',
             'fit': 'Model and effort that ran in Claude Code compared with the model guide',
             'suggest': 'Facts for choosing a Claude model and effort for a session now'}
    for name in ('version', 'check-update', 'update', 'run') + COLLECTOR_COMMANDS:
        command = commands.add_parser(name, allow_abbrev=False, help=helps.get(name),
                                      epilog='Collector options are forwarded, e.g. --json --provider claude --days 7. Use -- --help for all collector options.' if name == 'run' or name in COLLECTOR_COMMANDS else None)
        command.add_argument('--data-dir', help='Local reports and update-state directory')
        if name == 'run' or name in COLLECTOR_COMMANDS:
            command.add_argument('--offline', action='store_true', help='Skip all update network requests')
    for name, modes, text in (('rules', ['on', 'off', 'status', 'show', 'apply'], 'The model and effort hint in Claude Code CLAUDE.md'),
                              ('autopilot', ['on', 'off', 'status', 'show'], 'Model and effort chosen per subagent, kept in the same CLAUDE.md block')):
        command = commands.add_parser(name, allow_abbrev=False, help=text)
        command.add_argument('mode', nargs='?', default='status', choices=modes)
        command.add_argument('--data-dir', help='Local reports and state directory')
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
    if forwarded and args.command != 'run' and args.command not in COLLECTOR_COMMANDS:
        cli.error('unrecognized arguments: ' + ' '.join(forwarded))
    root = skill_root()
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
        # (skill directory, whether Claude Code sub-skill links go next to it). The sub-skills
        # are about Claude models, so the Codex skill gets none.
        if args.dest:
            destinations = [(Path(args.dest).expanduser().absolute() / 'asi', args.target == 'claude')]
        else:
            destinations = []
            if args.target in ('codex', 'both'):
                destinations.append((Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex').expanduser().absolute() / 'skills/asi', False))
            if args.target in ('claude', 'both'):
                destinations.append((claude_directory() / 'skills/asi', True))
        cli_path = None
        if args.cli_dir:
            cli_path = Path(args.cli_dir).expanduser().absolute() / 'asi'
            cli_body = '#!/bin/sh\n# ASI CLI launcher\nexec python3 ' + shlex.quote(str(destinations[0][0] / 'scripts/asi.py')) + ' "$@"\n'
            if cli_path.is_symlink() or (cli_path.exists() and cli_path.read_text() != cli_body):
                raise UpdateError('Existing terminal command preserved: ' + str(cli_path))
        kept = 0
        for destination, links in destinations:
            version = install_files(destination, manifest, files, allow_downgrade=args.allow_downgrade)
            print('Installed ASI ' + version + ' at ' + str(destination))
            remove_legacy_install(destination)
            if links:
                kept += link_subskills(destination)
        if cli_path is not None:
            cli_path.parent.mkdir(parents=True, exist_ok=True)
            cli_path.write_text(cli_body)
            cli_path.chmod(0o755)
            print('Installed terminal command at ' + str(cli_path))
            alias_legacy_cli(cli_path)
        if kept:
            # ASI itself is installed; only those slash commands are missing.
            print(str(kept) + (' sub-skill was' if kept == 1 else ' sub-skills were') + ' not linked (see above); '
                  'ASI itself is installed', file=sys.stderr)
        return 0
    if forwarded[:1] == ['--']:
        forwarded = forwarded[1:]
    if args.command == 'menubar' and not forwarded:
        return launch_menubar()
    # Commands that only read never move the 1.x data directory; every other one may write to it.
    read_only = args.command == 'version' or (args.command in ('rules', 'autopilot') and args.mode in ('status', 'show'))
    data = data_directory(args.data_dir, move=not read_only)
    if data == root.resolve() or root.resolve() in data.parents:
        raise UpdateError('Choose a data directory outside the installed skill')
    if args.command in ('rules', 'autopilot'):
        # Local file edits only: no collector, no update check.
        return rules_command(data, args.command, args.mode)
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
    mode = [args.command] if args.command in COLLECTOR_COMMANDS else []
    return subprocess.call([sys.executable, str(runtime)] + mode + ['--output', str(data / 'output')] + forwarded)

if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, UpdateError, zipfile.BadZipFile) as error:
        raise SystemExit('Error: ' + str(error))
