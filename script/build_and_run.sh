#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-run}"
case "$MODE" in
  run|--build-only|--verify|--snapshot|--logs|--telemetry|--debug) ;;
  *) echo "usage: $0 [--build-only|--verify|--snapshot DIRECTORY|--logs|--telemetry|--debug]" >&2; exit 2 ;;
esac
if [[ "$MODE" == "--snapshot" && -z "${2:-}" ]]; then
  echo "--snapshot requires an output directory" >&2; exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_NAME="AISADMenuBar"
APP_BUNDLE="$ROOT_DIR/dist/$APP_NAME.app"
if [[ "$MODE" != "--build-only" && "$MODE" != "--snapshot" ]]; then
  pkill -x "$APP_NAME" >/dev/null 2>&1 || true
fi
swift build --package-path "$ROOT_DIR/macos" --product "$APP_NAME"
BUILD_DIR="$(swift build --package-path "$ROOT_DIR/macos" --show-bin-path)"

mkdir -p "$APP_BUNDLE/Contents/MacOS" "$APP_BUNDLE/Contents/Resources"
# Replace the executable atomically so macOS does not reuse its old code cache.
cp "$BUILD_DIR/$APP_NAME" "$APP_BUNDLE/Contents/MacOS/$APP_NAME.new"
mv -f "$APP_BUNDLE/Contents/MacOS/$APP_NAME.new" "$APP_BUNDLE/Contents/MacOS/$APP_NAME"
cp "$ROOT_DIR/agent_usage.py" "$APP_BUNDLE/Contents/Resources/agent_usage.py"
cp "$ROOT_DIR/provider_limits.py" "$APP_BUNDLE/Contents/Resources/provider_limits.py"
python3 - "$APP_BUNDLE/Contents/Info.plist" "$ROOT_DIR/agent_usage.py" <<'PY'
import ast
import plistlib
import sys
from pathlib import Path

module = ast.parse(Path(sys.argv[2]).read_text())
version = next(ast.literal_eval(node.value) for node in module.body
               if isinstance(node, ast.Assign)
               and any(isinstance(target, ast.Name) and target.id == 'VERSION' for target in node.targets))
with open(sys.argv[1], 'wb') as target:
    plistlib.dump(dict(CFBundleExecutable='AISADMenuBar', CFBundleIdentifier='com.aiatsuk.aisad.menubar',
                      CFBundleName='AISAD', CFBundleDisplayName='AISAD', CFBundlePackageType='APPL',
                      CFBundleShortVersionString=version, CFBundleVersion=version,
                      LSMinimumSystemVersion='14.0', LSUIElement=True, NSPrincipalClass='NSApplication'),
                 target)
PY

case "$MODE" in
  --build-only) echo "$APP_BUNDLE" ;;
  --debug) lldb -- "$APP_BUNDLE/Contents/MacOS/$APP_NAME" ;;
  --logs|--telemetry)
    /usr/bin/open -n "$APP_BUNDLE"
    /usr/bin/log stream --info --style compact --predicate "process == \"$APP_NAME\"" ;;
  --verify)
    /usr/bin/open -n "$APP_BUNDLE"
    sleep 1
    pgrep -x "$APP_NAME" >/dev/null
    echo "AISAD menu bar process is running." ;;
  --snapshot)
    /usr/bin/open -n "$APP_BUNDLE" --args --snapshot "$2" "${@:3}"
    echo "Rendering native light/dark snapshots in $2" ;;
  run) /usr/bin/open -n "$APP_BUNDLE" ;;
esac
