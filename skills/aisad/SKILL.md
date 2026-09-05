---
name: aisad
description: Report local Claude Code and Codex usage as text or JSON, diagnose session cost drivers, show a live terminal status line, build a dashboard, and update AISAD. Use for usage, cost checks, model routing, context or cache analysis, spend pools, and AISAD installation or updates.
---

# AISAD

Use the `scripts/aisad.py` helper relative to this skill's directory. It bundles the collector in released installations and manages updates from **https://github.com/aiatsuk/aisad**. It requires Python 3.9+ and no third-party packages.

## Quick usage and analysis

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
- `current.diagnostics`, `previous.diagnostics`: session findings, trace coverage, associated cost and conditional savings. `analysis_rules` documents check thresholds and actions.
- `current.analysis_records`, `previous.analysis_records`: optional per-request check evidence and numeric trace statistics with `--include-requests`.
- `pools`, `pool_scope`: interactive and managed spend for the selected dates across all providers and projects. These totals intentionally ignore analysis filters.
- `quality`, `scan`, `source_summary`: collection diagnostics across all discovered history, not the selected period. `unknown_models` covers the current filtered period.

Answer the user's question by computing from these fields with local Python or other local tools. For example, rank `by_model` for the most expensive models, compare each model's known cost across periods for cost drivers, or use `by_session` for expensive sessions. Avoid dumping the entire JSON into the conversation. For request-level questions, rerun with `--include-requests`. The full normalized history and price catalog are also saved as `usage.json` and `prices-used.json`.

Preserve null prices, partial totals and cache-TTL ranges. Compare costs only when pricing is complete and exact in both periods; report unavailable comparisons explicitly. Do not invent zero usage for missing records. Costs are API-equivalent estimates, not subscription charges. Token volume does not measure productivity or output quality.

## Cost check and recommendations

For `analyze`, cost checks, efficiency questions or possible savings:

```sh
python3 <skill-directory>/scripts/aisad.py analyze
python3 <skill-directory>/scripts/aisad.py analyze --json --include-requests
python3 <skill-directory>/scripts/aisad.py analyze --json --provider claude --days 30
```

This collects local traces without HTML or a server. Eight checks cover model routing candidates, large first observed context, large tool/MCP payloads, sustained context growth, possible cache rebuilds after pauses, long-context price premiums, premium processing modes, and repeated polling. Missing message/tool telemetry makes payload and polling checks unavailable; it does not mean no waste. Uber's article names four examples of its internal 16 checks; do not claim AISAD replicates all 16.

For each relevant finding, report the evidence, associated request cost, and one targeted next step. `known_cost_usd` is associated spend, not wasted money. Findings overlap; never add their costs or savings together. Use the top-level `diagnostics.scenario_savings_usd` / `scenario_savings_high_usd`, which take the largest single scenario per request. Preserve nulls when no saving was modeled and identify partial pricing.

Model routing holds observed token usage fixed and requires a correctness/retry benchmark; a short session does not prove a simple task. A pause plus a cache drop suggests a rebuild, but does not prove expiration. First observed input cannot isolate system instructions from user/context input. Tool bytes are measured, not translated into billed tokens. Long-context premiums explain a rate difference, not guaranteed savings. Do not change the user's model, prompts, cache settings or budgets just because a check fires.

## Live status line and local budgets

```sh
python3 <skill-directory>/scripts/aisad.py statusline --offline
python3 <skill-directory>/scripts/aisad.py statusline --offline --watch 5 --budget 500
python3 <skill-directory>/scripts/aisad.py statusline --offline --json --session Codex:SESSION_ID
```

The line shows the lifetime recorded session estimate, provider total for the selected period, shared interactive pool, optional managed pool, context/cache counters and a short coaching tip. Resolve the user's session explicitly when possible. `CODEX_THREAD_ID` is used when present; otherwise the latest recorded session is clearly labeled. Never describe a latest-observed fallback as the active session. `--watch` prints terminal updates only; stop the process on request. JSON watch output is one object per update (NDJSON).

`--budget USD` sets optional expected spend for the selected period, shared across interactive providers/projects. `--managed-budget USD` sets a separate pool. `--managed-session PROVIDER:ID` explicitly tags a session and confirmed descendants; repeat for additional roots. Subagents do not automatically enter the managed pool. `--pool interactive|managed` filters analysis. Budgets provide visible 50/80/100% nudges, without caps or external messages. If the user requests a budget without an amount, ask for it; never invent one.

Claude Code can invoke `statusline --offline --stdin` through its command status-line hook; stdin supplies `session_id`. For a requested integration, preserve other settings and resolve the installed helper's absolute path. The [README](https://github.com/aiatsuk/aisad#claude-code-status-line-integration) includes a `statusLine` example. Use `--offline` in this frequent hook. AISAD also runs beside Codex in a terminal; do not claim its custom line is installed in Codex's native footer.

## Dashboard

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

`--target claude` installs into the Claude Code skills directory; `--target both` installs both. The defaults honor `CODEX_HOME` and `CLAUDE_CONFIG_DIR`. `--dest /path/to/skills` selects a custom parent directory. Installation uses the latest stable release; `--version 2.4.0` selects an explicit published version. The repository README documents release and offline installation options.
