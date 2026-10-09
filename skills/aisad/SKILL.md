---
name: aisad
description: Analyze local Claude Code and Codex usage on demand, with text or JSON reports, session evidence and an offline dashboard. Uses existing files without hooks, MCP integration or background monitoring.
---

# AISAD

Use the bundled standalone collector when the user asks about local session usage or requests a report. Each invocation reads existing local files on demand; the interactive chart waits for keyboard input and exits with Q/Escape. Do not install hooks, MCP servers, OpenTelemetry exporters, app-server observers, polling, scheduled tasks or startup services. Do not modify either application's settings. The skill is an optional command launcher, not instrumentation.

Every command that reads sessions stays offline. `prices --refresh` is the one exception: it reads published rates and sends nothing about local usage.

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

Preserve null prices and cache-TTL ranges. A known subtotal is not a complete bill. Cost totals and cost comparisons cover priced requests only: `cost_comparison_basis` names that basis, `changes.estimated_cost_usd` reports `excluded_current_requests` and `excluded_previous_requests`, and `--include-requests` adds `pricing_coverage`. Report those exclusions with any cost figure. Missing dates do not establish zero usage. Ordinary usage answers should stay focused on statistics; recommendations and hypothetical savings remain disabled.

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

## Spend forecast (optional)

`budget --forecast on|off` and `budget --quantile Q` (0.5–0.99, default 0.8) switch the deterministic forecast; `forecast [--json]` prints the frozen weekly and monthly forecast, a suggested budget quantile, pace, calibration state, confidence and pricing coverage. It needs three complete Monday–Sunday weeks and writes `forecast.json` once per period. It is a statistical projection of known cost, not advice: present the numbers with their calibration and confidence, never change the saved limit unless the user asks for `budget --set`, and keep recommendations and hypothetical savings disabled.

## Terminal chart and budget

```sh
python3 <skill-directory>/scripts/aisad.py chart --offline --color
python3 <skill-directory>/scripts/aisad.py chart --offline --color --interactive
python3 <skill-directory>/scripts/aisad.py chart --offline --color --view weeks --snapshot
python3 <skill-directory>/scripts/aisad.py budget
python3 <skill-directory>/scripts/aisad.py budget --set 3000
python3 <skill-directory>/scripts/aisad.py budget --reset
```

For a requested visual terminal chart, execute `chart --offline --color` and show the actual terminal output. Do not recreate the graph in an assistant message, strip its colors, switch to `--ascii`, or substitute an ASCII code block. If the chat surface cannot display ANSI colors, provide the command to run in the user's terminal instead of pretending a text reconstruction is the chart. Use `--ascii` only when the user explicitly asks for ASCII compatibility.

When its checked bundle and Bun are available, the interactive chart uses a strict TypeScript/React/Ink UI with live resize and automatic terminal cleanup. Its input contains only monthly numeric aggregates, never transcripts or source paths. It keeps the same W/H/L/Q controls. Without Bun/the bundle, the portable Python UI remains available; `AISAD_TERMINAL_UI=python` selects it explicitly. Snapshot/JSON commands never launch that UI. No runtime package installation or network connection is needed. Brief Ink morphs accompany month navigation while exact amounts remain text. A two-row minimap shows the selected month's actual daily costs in provider colors in both views, covering the full calendar month with thin curves and a shared monthly peak scale; corresponding provider/day samples morph smoothly and newly present samples fade in place; missing days stay blank and unpriced days show `?`. `AISAD_REDUCED_MOTION=1`, screen readers, ASCII, no-color output and CI disable movement; Python, snapshots and statusline remain static. Animation never implies new data or continuous collection.

`chart` renders a calendar-month daily cost chart with rounded Unicode step lines, daily number/weekday labels (weekends highlighted), and colored Claude/Codex lines and other providers when local data exists. Missing/future days stay blank, wholly unpriced days show `?`, and JSON retains incomplete-coverage metadata. Grok uses separately labelled provider-reported costs; the existing shared budget still covers Claude/Codex. `--json` exposes exact daily costs and coverage; `--ascii`, `--width`, `--height`, `--color` and `--no-color` control rendering. In a terminal, W toggles a Sunday-first weekday cost matrix, H/L or left/right arrows change months, and Q/Escape exits. The matrix has one column per calendar week with only the known daily cost in each cell; a Total row sums known weekly spend. Five spend levels use primary text through warm colors. Script-generated Insights summarize the recent 28 completed days, expensive weekdays and an approximate shared-budget forecast; no LLM or network is involved. `--month YYYY-MM` selects a month, `--view weeks` starts with the table, and `--snapshot` prints once. Piped output and JSON always remain one-shot. Keyboard navigation reuses one local snapshot, without polling or background collection. No server, watch loop or new hooks are installed.

`budget` is always offline and does not collect sessions. `--set USD` saves a finite positive monthly limit in the data directory's `output/budget.json`; `--reset` restores $2,000. Statusline and chart use this value unless `--monthly-budget` overrides it. Change the saved limit only when requested. For a requested terminal launcher installation, the installer accepts `--cli-dir DIR`; it does not edit shell settings or overwrite an unrelated command.

## Prices

```sh
python3 <skill-directory>/scripts/aisad.py prices            # what is stored locally
python3 <skill-directory>/scripts/aisad.py prices --refresh  # read published rates now
```

Rates come from models.dev, refreshed at most once every 24 hours by the launcher alongside its update check; `--offline` or `AISAD_AUTO_PRICES=0` disables that. Reports name their basis in `price_as_of`, `price_basis` and `price_sources` — read those rather than assuming a catalog. A failed refresh keeps the rates already stored, so a report never waits on the network or changes because a fetch failed.

The published source supplies base rates, context tiers and fast-mode rates. It does not publish one-hour cache writes or flex/batch discounts, which keep their built-in values, and a model it omits keeps its built-in rate. `--prices FILE` still overrides everything. Refreshed rates do not restate history: the catalog applies current prices to all recorded dates.

## Offline dashboard

```sh
python3 <skill-directory>/scripts/aisad.py run -- --open
```

This creates and opens one self-contained HTML snapshot, then exits. It has Charts, Sessions, Context and Cache usage; no server or browser polling is needed. If the host cannot open the file, present its local path. The offline preview retains at most the latest 200 metadata events per session; use session JSON or SQLite for complete history. Opening the HTML does not gather new data; rerun the command when requested.

`statusline` prints one compact line and exits: today, calendar-week-to-date spend versus the same weekdays last week, month-to-date spend versus matched days in the previous month, then a six-cell budget bar and percentage. Shorter previous months explicitly label the matched-day subtotals. The monthly budget defaults to $2,000; `--monthly-budget USD` overrides it. Monthly spend includes every discovered Claude/Codex session and agent pool, independent of filters and selected dates. JSON retains matched-day monthly comparison metadata. Coral changes to amber at 65%, orange at 80% and red at 100%, against a dark gray background. `--color` forces colors in piped output; `--no-color` disables them. Text keeps monetary amounts and budget percentages uncluttered; only comparison deltas use a positive sign. JSON retains incomplete-pricing metadata. It has no watch or stdin mode. Do not build monitors around it or configure external status hooks.

## Updates and local data

```sh
python3 <skill-directory>/scripts/aisad.py version
python3 <skill-directory>/scripts/aisad.py check-update
python3 <skill-directory>/scripts/aisad.py update
```

The helper checks for newer stable releases at most once per 24 hours when a command is invoked, and refreshes published rates on the same schedule. It does not install a scheduler. Those requests download public GitHub release metadata, code and the models.dev catalog only, without uploading sessions or metrics. Add `--offline` to reporting commands to skip every network request. `AISAD_AUTO_UPDATE=0` disables update checks and `AISAD_AUTO_PRICES=0` disables price refreshes; explicit commands still work.

Updates replace the skill, launcher and collector together, verify release checksums and the manifest, and refuse to overwrite local edits. If an update occurred, reread the installed SKILL.md before interpreting its output. A failed automatic check keeps the current installation usable. Existing HTML snapshots do not update themselves.

Reports default to `~/.local/share/aisad/output`, outside the replaceable installation. `AISAD_DATA_DIR` or `--data-dir` selects another local directory. Collector options are forwarded by the helper; `run -- --codex-dir /local/codex --claude-dir /local/claude` selects different source directories. Removed source files disappear from the next derived snapshot.

Keep all session data local. Do not upload real reports or use them for public examples. Session titles remain disabled unless requested; metadata and source paths can still identify projects. Use synthetic profiles for screenshots and release assets.

## Installation

From a clone of `aiatsuk/aisad`:

```sh
python3 skills/aisad/scripts/aisad.py install --target codex
```

`--target claude` installs for Claude Code and `--target both` installs both. Defaults honor `CODEX_HOME` and `CLAUDE_CONFIG_DIR`; `--dest` chooses a custom skills parent. The package includes the standalone collector. A raw skill checkout downloads its runtime on first use; a bundled release works offline immediately. The repository README documents offline archives, checksums and explicit version selection. Use `--allow-downgrade` only for a user-requested lower version; it never bypasses preservation of local edits.
