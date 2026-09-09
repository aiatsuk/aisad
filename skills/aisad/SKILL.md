---
name: aisad
description: Analyze local Claude Code and Codex usage on demand, with text or JSON reports, session evidence and an offline dashboard. Uses existing files without hooks, MCP integration or background monitoring.
---

# AISAD

Use the bundled standalone collector when the user asks about local session usage or requests a report. Each invocation reads existing local files and exits. Do not install hooks, MCP servers, OpenTelemetry exporters, app-server observers, polling, scheduled tasks or startup services. Do not modify either application's settings. The skill is an optional command launcher, not instrumentation.

## Quick usage

Resolve this skill's directory and run its helper:

```sh
python3 <skill-directory>/scripts/aisad.py usage
```

Default to the last seven calendar days ending on the collection date. Example output:

```text
For Aug 30–Sep 5: $1,327.32 estimated API cost. In: 29M, Out: 1.28M
```

Use the actual output, not these illustrative values. `In` includes uncached input, cache reads and cache writes. `Out` excludes input. Costs are API-equivalent estimates, not subscription charges or invoices.

For questions requiring calculations:

```sh
python3 <skill-directory>/scripts/aisad.py usage --json
python3 <skill-directory>/scripts/aisad.py usage --json --provider claude --days 30
python3 <skill-directory>/scripts/aisad.py usage --json --include-requests
```

Usage JSON remains `schema_version: 2`. Read `period`, `previous_period`, `filters`, `current.totals`, `changes`, and the relevant `by_model`, `by_provider`, `by_project`, `by_session`, `by_role` or `by_date` breakdown. `current.rows` provides joint groups; distinct session counts must not be summed across models or days. `--include-requests` adds normalized usage observations and `request_stats`, including event IDs and source references. `quality` and `scan` describe collection coverage over discovered history.

Preserve null prices and cache-TTL ranges. A known subtotal is not a complete bill. Read the installed version's comparison status and pricing coverage: current versions may compare priced subtotals while reporting excluded observations. Missing dates do not establish zero usage. Ordinary usage answers should stay focused on statistics; recommendations and hypothetical savings remain disabled.

A usage answer is computed from usage observations alone, so `usage`, `analyze` and `statusline` do not refresh `sessions.sqlite` or `usage.json`. Their totals cover every discovered trace either way. Run `collect` when the evidence database itself must be current.

## Session evidence and custom analysis

```sh
python3 <skill-directory>/scripts/aisad.py collect --json
python3 <skill-directory>/scripts/aisad.py sessions --json
python3 <skill-directory>/scripts/aisad.py session --session Codex:SESSION_ID --json
python3 <skill-directory>/scripts/aisad.py session --session Claude:SESSION_ID --tree --all-time --json
python3 <skill-directory>/scripts/aisad.py session --session Codex:SESSION_ID --json --offset 200 --limit 200
python3 <skill-directory>/scripts/aisad.py usage --json --include-requests --include-events
```

These commands collect on request; none keeps observing the tools afterward. They publish the evidence database, rewriting only the sessions whose traces changed since the last collection, so a repeat run costs a fraction of the first. Find a real provider-prefixed session ID from `sessions`, rather than guessing it. Session reports and the SQLite event database use evidence schema version 1, separate from usage schema version 2. `--from`, `--to`, `--days`, `--all-time`, provider/model/project/role/pool filters work on these reports. Follow `next_offset` for additional events; default pages contain 200 and the maximum is 10,000.

- `sessions[].own` covers that session's observations within the selected dates/model/pool. `tree` includes confirmed descendants once; tree totals overlap and must not be summed.
- `lifecycle` and explicitly named `lifetime` fields describe all observed history. Last seen and a completed turn do not prove a session's current state. State stays unknown; elapsed time includes idle time, and active time is unavailable.
- `events` contains allowlisted metadata only. `evidence` gives source-file IDs, line numbers, byte offsets and parsed-record fingerprints. `source_files` resolves paths for the page. `tools` reports calls, result bytes, recorded errors and observed call-to-result intervals.
- `measurement_basis` identifies measured, estimated and unavailable quantities. Input counts do not establish context composition or quality. Result bytes do not establish billed tokens, loaded definitions or repeated inclusion. Cache changes alone do not prove expiration.

For broad queries, use local Python and open `output/sessions.sqlite` read-only (`mode=ro`). Tables include `sessions`, `turns`, `events`, `event_sources`, `source_files`, `usage_observations`, `observation_events`, `tool_calls`, `context_snapshots` and `metadata`. The current price catalog and measurement definitions are in metadata. Use SQL to select only the needed rows, then compute the answer locally; avoid dumping the full history into the conversation.

Original prompts, answers, reasoning, tool arguments/results and compaction summaries are not copied into reports or the database. Source references can locate original records while the local files still exist; fingerprints detect changes. Do not reconstruct missing payloads or infer exact tool cost from byte counts.

## Offline dashboard

```sh
python3 <skill-directory>/scripts/aisad.py run -- --open
```

This creates and opens one self-contained HTML snapshot, then exits. It has Charts, Sessions, Context and Cache usage; no server or browser polling is needed. If the host cannot open the file, present its local path. The offline preview retains at most the latest 200 metadata events per session; use session JSON or SQLite for complete history. Opening the HTML does not gather new data; rerun the command when requested.

`statusline` remains a manually invoked one-shot snapshot for compatibility. `--watch` and `--stdin` are no longer supported. Do not create replacement monitors or configure external status hooks.

## Updates and local data

```sh
python3 <skill-directory>/scripts/aisad.py version
python3 <skill-directory>/scripts/aisad.py check-update
python3 <skill-directory>/scripts/aisad.py update
```

The helper checks for newer stable releases at most once per 24 hours when a command is invoked. It does not install a scheduler. Checks download public GitHub release metadata and code only, without uploading sessions or metrics. Add `--offline` to reporting commands to skip all update requests. `AISAD_AUTO_UPDATE=0` disables automatic update checks; explicit update commands still work.

Updates replace the skill, launcher and collector together, verify release checksums and the manifest, and refuse to overwrite local edits. If an update occurred, reread the installed SKILL.md before interpreting its output. A failed automatic check keeps the current installation usable. Existing HTML snapshots do not update themselves.

Reports default to `~/.local/share/aisad/output`, outside the replaceable installation. `AISAD_DATA_DIR` or `--data-dir` selects another local directory. Collector options are forwarded by the helper; `run -- --codex-dir /local/codex --claude-dir /local/claude` selects different source directories. Removed source files disappear from the next derived snapshot.

Keep all session data local. Do not upload real reports or use them for public examples. Session titles remain disabled unless requested; metadata and source paths can still identify projects. Use synthetic profiles for screenshots and release assets.

## Installation

From a clone of `aiatsuk/aisad`:

```sh
python3 skills/aisad/scripts/aisad.py install --target codex
```

`--target claude` installs for Claude Code and `--target both` installs both. Defaults honor `CODEX_HOME` and `CLAUDE_CONFIG_DIR`; `--dest` chooses a custom skills parent. The package includes the standalone collector. A raw skill checkout downloads its runtime on first use; a bundled release works offline immediately. The repository README documents offline archives, checksums and explicit version selection. Use `--allow-downgrade` only for a user-requested lower version; it never bypasses preservation of local edits.
