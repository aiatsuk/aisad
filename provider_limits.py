#!/usr/bin/env python3
"""Read subscription quotas only. No prompts, model calls, credential writes or token refresh."""
import argparse
import concurrent.futures
import datetime as dt
import json
import math
import os
from pathlib import Path
import selectors
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

NAMES = {"claude": "Claude Code", "codex": "Codex", "grok": "Grok"}
CHILDREN = set()
LOCK = threading.RLock()
MAX_BYTES = 1_048_576


class Unavailable(Exception):
    def __init__(self, message, status="unavailable", retry=60):
        self.message, self.status, self.retry = message, status, retry


def stamp(value=None):
    return (value or dt.datetime.now(dt.timezone.utc)).isoformat()


def date(value):
    try:
        if isinstance(value, bool):
            return None
        if isinstance(value, (float, int)) and math.isfinite(value):
            return stamp(dt.datetime.fromtimestamp(value, dt.timezone.utc))
        if isinstance(value, str):
            parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
            return stamp(parsed) if parsed.tzinfo is not None else None
    except (ValueError, OverflowError, OSError):
        pass
    return None


def numeric(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def window(identifier, title, used, reset, minutes):
    if not numeric(used) or used < 0:
        return None
    return dict(id=identifier, title=title, used_percent=used, resets_at=date(reset),
                duration_minutes=minutes if numeric(minutes) and minutes > 0 else None)


def parse_claude(payload):
    result = []
    for index, entry in enumerate(payload.get("limits") or []):
        if not isinstance(entry, dict):
            continue
        kind = entry.get("kind")
        title = {"session": "5 hours", "weekly_all": "Weekly"}.get(kind)
        if kind == "weekly_scoped":
            scope = entry.get("scope")
            model_info = scope.get("model") if isinstance(scope, dict) else None
            model = model_info.get("display_name") if isinstance(model_info, dict) else None
            if isinstance(model, str) and model and len(model) <= 32:
                title = "Weekly · " + model
        if title:
            row = window("limit-" + str(index), title, entry.get("percent"),
                         entry.get("resets_at"), 300 if kind == "session" else 10080)
            if row:
                result.append(row)
    for key, body in payload.items():
        title = {"five_hour": "5 hours", "seven_day": "Weekly"}.get(key)
        if key.startswith("seven_day_") and key[10:] in ("fable", "opus", "sonnet", "haiku", "mythos"):
            title = "Weekly · " + key[10:].capitalize()
        if title and isinstance(body, dict):
            row = window(key, title, body.get("utilization"), body.get("resets_at"),
                         300 if key == "five_hour" else 10080)
            if row and not any(x["title"] == row["title"] for x in result):
                result.append(row)
    # New Claude releases may put model-specific weekly meters in limits[].
    for index, entry in enumerate(payload.get("limits") or []):
        if not isinstance(entry, dict):
            continue
        scoped = entry.get("weekly_scoped")
        if not isinstance(scoped, dict):
            continue
        label = scoped.get("model") or scoped.get("scope") or scoped.get("name")
        if not isinstance(label, str) or not label or len(label) > 32:
            continue
        row = window("scoped-" + str(index), "Weekly · " + label,
                     scoped.get("utilization"), scoped.get("resets_at"), 10080)
        if row and not any(x["title"] == row["title"] for x in result):
            result.append(row)
    return result


def parse_codex(payload):
    buckets = payload.get("rateLimitsByLimitId")
    if not isinstance(buckets, dict) or not buckets:
        buckets = {"codex": payload.get("rateLimits")}
    result, plan = [], None
    for bucket_id, bucket in buckets.items():
        if not isinstance(bucket, dict):
            continue
        if bucket_id == "codex":
            plan = bucket.get("planType")
        for position in ("primary", "secondary"):
            body = bucket.get(position)
            if not isinstance(body, dict):
                continue
            minutes = body.get("windowDurationMins")
            title = "5 hours" if minutes == 300 else "Weekly" if minutes == 10080 else (
                str(minutes) + " min" if numeric(minutes) else "Quota")
            label = bucket.get("limitName")
            if bucket_id != "codex" and isinstance(label, str) and len(label) <= 32:
                title += " · " + label
            row = window(str(bucket_id) + "-" + position, title, body.get("usedPercent"),
                         body.get("resetsAt"), minutes)
            if row:
                result.append(row)
    return result, plan


def parse_grok(payload):
    config = payload.get("config") or {}
    period = config.get("currentPeriod") or {}
    reset = period.get("end") or config.get("billingPeriodEnd")
    start = date(period.get("start") or config.get("billingPeriodStart"))
    end = date(reset)
    minutes = None
    if start and end:
        minutes = (dt.datetime.fromisoformat(end) - dt.datetime.fromisoformat(start)).total_seconds() / 60
        if minutes <= 0:
            minutes = None
    title = "Weekly" if minutes and abs(minutes - 10080) <= 60 else (
        "Monthly" if minutes and 27 * 1440 <= minutes <= 32 * 1440 else "Credits")
    # A missing percentage is unknown, including a period with a prepaid wallet.
    row = window("credits", title, config.get("creditUsagePercent"), reset, minutes)
    return [row] if row else []


def stop_child(process):
    with LOCK:
        CHILDREN.discard(process)
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=0.15)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        except ProcessLookupError:
            pass


def cancel(_signal, _frame):
    with LOCK:
        children = list(CHILDREN)
    for process in children:
        stop_child(process)
    raise SystemExit(130)


def executable(name):
    found = shutil.which(name)
    if found:
        return found
    for directory in [Path.home() / ".local/bin", Path("/opt/homebrew/bin"), Path("/usr/local/bin")]:
        path = directory / name
        if os.access(path, os.X_OK) and path.is_file():
            return str(path)
    raise Unavailable("Install " + NAMES[name] + " CLI and sign in there.", "not_connected", 300)


def rpc(name, arguments, initialize, method):
    process = subprocess.Popen([executable(name)] + arguments, stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               start_new_session=True)
    with LOCK:
        CHILDREN.add(process)
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    pending, total = b"", 0
    deadline = time.monotonic() + 20

    def send(item):
        process.stdin.write((json.dumps(item) + "\n").encode())
        process.stdin.flush()

    def read(wanted):
        nonlocal pending, total
        while time.monotonic() < deadline:
            if b"\n" not in pending:
                if not selector.select(max(0, deadline - time.monotonic())):
                    break
                data = os.read(process.stdout.fileno(), 65536)
                if not data:
                    break
                total += len(data)
                if total > MAX_BYTES:
                    raise Unavailable("Provider response was too large.")
                pending += data
            while b"\n" in pending:
                line, pending = pending.split(b"\n", 1)
                try:
                    item = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(item, dict):
                    continue
                if "method" in item and "id" in item:
                    send(dict(jsonrpc="2.0", id=item["id"],
                              error=dict(code=-32601, message="Read-only quota client")))
                elif item.get("id") == wanted:
                    if "error" in item:
                        code = (item.get("error") or {}).get("code")
                        raise Unavailable("This CLI cannot read plan limits." if code == -32601 else
                                          "Could not read limits. Check the CLI sign-in.",
                                          "unsupported" if code == -32601 else "not_connected", 300)
                    result = item.get("result")
                    if not isinstance(result, dict):
                        raise Unavailable("Provider returned an invalid quota response.")
                    return result
        raise Unavailable("Quota request timed out. Try Refresh.", retry=120)

    try:
        send(dict(jsonrpc="2.0", id=1, method="initialize", params=initialize))
        read(1)
        if name == "codex":
            send(dict(jsonrpc="2.0", method="initialized"))
        send(dict(jsonrpc="2.0", id=2, method=method, params={}))
        return read(2)
    finally:
        selector.close()
        stop_child(process)
        for stream in (process.stdin, process.stdout):
            if stream:
                stream.close()


def keychain_credentials():
    """Read the existing Claude login with Apple's credential client; never write it."""
    if sys.platform != "darwin":
        return None
    try:
        result = subprocess.run(
            ["/usr/bin/security", "find-generic-password", "-s", "Claude Code-credentials", "-w"],
            stdin=subprocess.DEVNULL, capture_output=True, timeout=3)
        if result.returncode != 0 or len(result.stdout) > MAX_BYTES:
            return None
        # This credential is only used for the provider request; never publish or persist it.
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, ValueError, OSError):
        return None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        return None


def claude():
    root = Path(os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude"))).expanduser()
    path = root / ".credentials.json"
    credentials = None
    if path.is_file() and path.stat().st_size <= MAX_BYTES:
        credentials = json.loads(path.read_text())
    elif root == Path.home() / ".claude":
        credentials = keychain_credentials()
    oauth = (credentials or {}).get("claudeAiOauth") or {}
    token = oauth.get("accessToken")
    if not isinstance(token, str) or not token:
        raise Unavailable("Claude sign-in is unavailable to AISAD.", "not_connected", 300)
    expires = oauth.get("expiresAt")
    if numeric(expires) and expires / 1000 <= time.time():
        raise Unavailable("Claude sign-in expired. Open Claude, then Refresh.", "not_connected", 300)
    request = urllib.request.Request("https://api.anthropic.com/api/oauth/usage",
        headers={"Authorization": "Bearer " + token, "anthropic-beta": "oauth-2025-04-20",
                 "Accept": "application/json", "User-Agent": "AISAD/1.4.3"})
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=12) as response:
            data = response.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise Unavailable("Provider response was too large.")
        payload = json.loads(data)
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            raise Unavailable("Claude usage access needs a current Claude sign-in.", "not_connected", 300)
        if error.code == 429:
            retry = error.headers.get("Retry-After", "300")
            retry = max(60, min(int(retry), 3600)) if retry.isdigit() and int(retry) > 0 else 300
            raise Unavailable("Claude requested a refresh cooldown.", "rate_limited", retry)
        raise Unavailable("Claude usage service is unavailable.", retry=120)
    return parse_claude(payload), None


def claude_worker():
    process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--claude-worker"],
                               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, start_new_session=True)
    with LOCK:
        CHILDREN.add(process)
    try:
        try:
            output, _ = process.communicate(timeout=18)
        except subprocess.TimeoutExpired:
            raise Unavailable("Claude sign-in could not be read in time.", "not_connected", 300)
        if process.returncode != 0 or len(output) > MAX_BYTES:
            raise Unavailable("Claude sign-in is unavailable to AISAD.", "not_connected", 300)
        return json.loads(output)
    finally:
        stop_child(process)


def fetch(name, direct=False):
    result = dict(id=name, name=NAMES[name], plan=None, source={
        "claude": "Claude OAuth", "codex": "Codex CLI", "grok": "Grok CLI"}[name],
        fetched_at=stamp(), status="available", message=None, retry_after_seconds=60, windows=[])
    try:
        if name == "claude":
            if not direct:
                return claude_worker()
            rows, plan = claude()
        elif name == "codex":
            payload = rpc(name, ["app-server", "--stdio"],
                          {"clientInfo": {"name": "aisad", "version": "1.4.3"}}, "account/rateLimits/read")
            rows, plan = parse_codex(payload)
        else:
            payload = rpc(name, ["agent", "stdio"],
                {"protocolVersion": 1, "clientInfo": {"name": "AISAD", "version": "1.4.3"},
                 "clientCapabilities": {}}, "_x.ai/billing")
            rows, plan = parse_grok(payload), payload.get("subscription_tier")
        if not rows:
            raise Unavailable("The provider did not report a quota percentage.", retry=120)
        result["windows"] = rows
        result["plan"] = plan if isinstance(plan, str) and len(plan) <= 32 else None
        result["fetched_at"] = stamp()
    except Unavailable as error:
        result.update(status=error.status, message=error.message, retry_after_seconds=error.retry)
    except Exception:
        # Never serialize exception text: an HTTP/client error could contain credentials.
        result.update(status="unavailable", message="Could not read usage. Try Refresh.",
                      retry_after_seconds=120)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--providers", nargs="+", choices=list(NAMES), default=list(NAMES))
    parser.add_argument("--claude-worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.claude_worker:
        print(json.dumps(fetch("claude", direct=True), allow_nan=False))
        return
    signal.signal(signal.SIGTERM, cancel)
    signal.signal(signal.SIGINT, cancel)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        providers = list(pool.map(fetch, dict.fromkeys(args.providers)))
    print(json.dumps(dict(schema_version=1, generated=stamp(), providers=providers), allow_nan=False))


if __name__ == "__main__":
    main()
