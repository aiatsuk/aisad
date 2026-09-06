---
name: aisad
description: Collect and show local Claude Code and Codex usage as text, JSON, a dashboard or a live terminal status line. Use for token and estimated cost statistics, period comparisons, model/provider/session breakdowns, cache and tool counts, spend pools, and AISAD installation or updates.
---

# AISAD

Use the `scripts/aisad.py` helper relative to this skill's directory. It bundles the collector in released installations and manages updates from **https://github.com/aiatsuk/aisad**. It requires Python 3.9+ and no third-party packages.

## Quick usage and statistics

For `usage`, collect local metrics and return the default weekly summary without generating HTML or starting a server:

```sh
python3 <skill-directory>/scripts/aisad.py usage
```

Example format: `For Aug 30–Sep 5: $1,327.32 estimated API cost. In: 29M, Out: 1.28M` Use the actual command output, never these example numbers. `In` is total input tokens, including cache reads and writes; `Out` is output tokens. Compact counts use K/M/B/T with up to two decimals. Include the previous-period cost and token comparison when available. Exact token totals, request counts and session counts remain in JSON.

For questions about costs, models, sessions, projects or trends, collect structured data and process it locally:

```sh
python3 <skill-directory>/scripts/aisad.py usage --json
python3 <skill-directory>/scripts/aisad.py usage --json --provider claude --days 30
python3 <skill-directory>/scripts/aisad.py usage --json --from 2026-08-30 --to 2026-09-05 --model gpt-6-astra
python3 <skill-directory>/scripts/aisad.py usage --json --all-time --include-requests
```

Filters: `--provider` accepts Codex/OpenAI or Claude/Anthropic; `--model`, `--project` and `--role main|subagent|review` narrow both periods. `--from` and `--to` are inclusive dates in the report timezone. Default to seven calendar days ending on the snapshot date. All time has no comparison.

JSON stdout is machine-readable; update messages go to stderr. The same report is saved as `output/usage-report.json` inside the data directory. Read only the fields needed for the question:

- `period`, `previous_period`, `filters`, `timezone`: scope of the answer.
- `current.totals`, `previous.totals`, `changes`: totals, weighted cache share, and comparison validity.
- `current.by_model`, `by_provider`, `by_project`, `by_role`, `by_session`, `by_date`: sorted breakdowns; the same keys exist under `previous`.
- `current.rows`: joint date/provider/model/session/project/role groups for cross-filtering. Session counts are distinct within each group and must not be added across models or days.
- `current.requests` and `previous.requests`: optional normalized per-request evidence with `--include-requests`; no conversation text.
- `current.telemetry`, `previous.telemetry`: message/tool telemetry coverage and measured tool/MCP counts and sizes.
- `current.pricing_coverage`, `previous.pricing_coverage`: priced/unpriced request counts and unpriced groups by provider, model and reason, with their input/output tokens.
- `current.request_stats`, `previous.request_stats`: optional per-request context, timing and numeric trace statistics with `--include-requests`.
- `pools`, `pool_scope`: interactive and managed spend for the selected dates across all providers and projects. These totals intentionally ignore the other filters.
- `price_basis`, `history_coverage`: current-rate versus custom-rate basis and observed date coverage by provider.
- `grok_usage`: separate completed-turn statistics from local Grok Build; reported cost, model calls, and incomplete turns for the selected dates across all Grok projects. These totals are not included in the Claude/Codex API estimate and do not use its provider/model filters.
- `quality`, `scan`, `source_summary`: collection diagnostics across all discovered history, not the selected period. `unknown_models` covers the current filtered period.

Answer the user's question by computing from these fields with local Python or other local tools. For example, rank `by_model` for the most expensive models, compare each model's known cost across periods for cost drivers, or use `by_session` for expensive sessions. Avoid dumping the entire JSON into the conversation. For request-level questions, rerun with `--include-requests`. The full normalized history and price catalog are also saved as `usage.json` and `prices-used.json`.

Preserve null prices and cache-TTL ranges. Exclude unpriced requests from cost totals and compare the known priced subtotals in both periods, disclosing excluded counts separately. Usage counts and tokens include all recorded requests. If a period has no priced requests, its cost comparison is unavailable rather than zero; price ranges still suppress a single percentage delta. Do not invent zero usage for missing records. The default catalog applies current prices to all historical records; it does not reconstruct historical bills. Costs are API-equivalent estimates, not subscription charges. Grok Build persists turn totals: show its provider-reported cost separately, since aggregate turns cannot be repriced reliably per request. Token volume does not measure productivity or output quality.

## Interpreting statistics

Usage and status-line reports use `schema_version: 2`. Read the installed version's fields: `telemetry` replaces `diagnostics`, `request_stats` replaces `analysis_records`, and rules, findings, hypothetical savings and coaching are no longer generated. `analyze` remains a compatibility alias for `usage`, with identical text/JSON output and filters.

Report measured totals, comparisons and breakdowns. Keep routine usage responses focused on statistics; do not append optimization recommendations. Use input tokens and numeric tool sizes to describe recorded context, not task difficulty or waste. Tool bytes do not identify billed token cost, and cache changes alone do not establish expiration. The full `usage.json` snapshot exposes numeric request statistics in `request_stats`.

## Live status line and local budgets

```sh
python3 <skill-directory>/scripts/aisad.py statusline --offline
python3 <skill-directory>/scripts/aisad.py statusline --offline --watch 5 --budget 500
python3 <skill-directory>/scripts/aisad.py statusline --offline --json --session Codex:SESSION_ID
```

The line shows the lifetime recorded session estimate, provider total for the selected period, shared interactive pool, optional managed pool, and context/cache counters. Resolve the user's session explicitly when possible. `CODEX_THREAD_ID` is used when present; otherwise the latest recorded session is clearly labeled. Never describe a latest-observed fallback as the active session. `--watch` prints terminal updates only; stop the process on request. JSON watch output is one object per update (NDJSON).

`--budget USD` sets optional expected spend for the selected period, shared across interactive providers/projects. `--managed-budget USD` sets a separate pool. `--managed-session PROVIDER:ID` explicitly tags a session and confirmed descendants; repeat for additional roots. Subagents do not automatically enter the managed pool. `--pool interactive|managed` filters statistics. Budgets show spend at the 50/80/100% thresholds, without caps or external messages. If the user requests a budget without an amount, ask for it; never invent one.

Claude Code can invoke `statusline --offline --stdin` through its command status-line hook; stdin supplies `session_id`. For a requested integration, preserve other settings and resolve the installed helper's absolute path. The [README](https://github.com/aiatsuk/aisad#claude-code-status-line-integration) includes a `statusLine` example. Use `--offline` in this frequent hook. AISAD also runs beside Codex in a terminal; do not claim its custom line is installed in Codex's native footer.

## Dashboard

The HTML includes a static usage summary so a script-disabled preview does not show empty statistics. Large snapshots are compressed inside the file and decoded locally in modern browsers. If the host blocks `file://` inspection, state that limitation and use an already available localhost dashboard for interactive checks; do not claim that testing HTTP verifies the file-preview path.

The period selector includes **This week (Mon–today)** and **Last week (Mon–Sun)**, anchored to the snapshot date in the report timezone. The current partial week compares with the same weekdays last week; the previous complete week compares with the week before it. Rolling seven-day, thirty-day, all-time and custom ranges remain available.

For a snapshot:

```sh
python3 <skill-directory>/scripts/aisad.py run
```

For an automatically refreshed dashboard:

```sh
python3 <skill-directory>/scripts/aisad.py run -- --watch 60
```

Read the resulting localhost URL from stdout and open it with the host application's browser tool, or add `--open` to the collector arguments. Reuse an existing dashboard process when appropriate. After an update, restart a running process only if you can identify it as one you started; running processes keep their loaded version until restarted.

`usage`, `analyze`, `statusline` and `run` check for a newer stable GitHub release at most once every 24 hours when invoked, apply an available update, and then run the collector. Updates replace this skill's instructions, helper and collector together. If code was updated, reread this SKILL.md before interpreting the results. A failed check keeps the installed version usable. Add `--offline` to any of these commands when the user wants no network activity; a first installation needs a bundled runtime or a successful update.

Output defaults to `~/.local/share/aisad/output`, outside the replaceable skill directory. `AISAD_DATA_DIR` or `--data-dir` selects a different data directory. Collector options go after `--`, for example `run -- --codex-dir /local/codex --claude-dir /local/claude`. Keep custom output outside the skill directory so updates preserve it.

## Check and update

```sh
python3 <skill-directory>/scripts/aisad.py version
python3 <skill-directory>/scripts/aisad.py check-update
python3 <skill-directory>/scripts/aisad.py update
```

`check-update` always checks GitHub but does not replace code. `update` checks and installs a newer stable release immediately. Automatic updates can be disabled persistently with `AISAD_AUTO_UPDATE=0`; explicit check/update commands still work. Do not implement polling, a scheduler or an OS startup service unless requested.

Updates download only public release metadata and code from the fixed repository. The helper verifies release checksums, manifest hashes and paths, refuses to overwrite local edits, and restores the previous installation if replacement fails. If an update is blocked by local modifications, keep those files and report the affected paths; do not delete or reset them to force an update.

## Local-only data

The collector reads only sources on the current device and exposes its dashboard only on `127.0.0.1`. Update requests contain no sessions, metrics, paths or device identifiers. Keep reports and conversation history on the device; they are not release assets. Do not upload real reports or use them in public screenshots. Session titles remain disabled unless the user asks for them.

## Installation on another device

Clone the repository, then run its helper:

```sh
python3 skills/aisad/scripts/aisad.py install --target codex
```

`--target claude` installs into the Claude Code skills directory; `--target both` installs both. The defaults honor `CODEX_HOME` and `CLAUDE_CONFIG_DIR`. `--dest /path/to/skills` selects a custom parent directory. Installation uses the latest stable release; `--version 1.0.1` selects an explicit published version. The repository README documents release and offline installation options.
