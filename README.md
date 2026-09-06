# AISAD — AI Session Analysis Dashboard

A portable, local-only usage dashboard for Claude Code and Codex. Track tokens, requests, estimated API costs, context and cache statistics, and keep a live spend counter in your terminal. Install the optional skill to ask questions about usage directly in Codex or Claude Code.

**Python 3.9+, standard library only.** No API keys, accounts, pip packages, Node.js or Codex plugins required. Collection and reporting happen on your device. The collector makes no outbound network requests; watch mode serves the dashboard on `127.0.0.1`. The optional skill checks GitHub for code updates without sending usage data, and supports offline use.

![AISAD dashboard with weekly comparisons, usage statistics and model costs](docs/dashboard.png)

*Example dashboard with synthetic sessions. The screenshot contains no personal usage data.*

## Quick start

Clone into a writable directory and start collecting:

```sh
git clone https://github.com/aiatsuk/aisad.git
cd aisad
python3 agent_usage.py --watch 60 --open
```

The dashboard opens in your browser and checks for local changes every minute. An available port is selected automatically. Press `Ctrl+C` to stop.

On macOS, you can also open `Run.command` from the repository folder. On Windows, use `py -3` instead of `python3`. If needed, install Python 3.9+ from [python.org](https://www.python.org/downloads/).

For a one-time snapshot without a running server:

```sh
python3 agent_usage.py --open
```

The generated HTML works offline. It includes a saved summary that remains readable before charts load, when JavaScript is disabled, or if initialization fails. Large snapshots use lossless embedded gzip compression; interactive views need a current browser with the [Compression Streams API](https://developer.mozilla.org/en-US/docs/Web/API/DecompressionStream). No data files are fetched. You can also copy just `agent_usage.py` to another device: the dashboard and price catalog are embedded in this one file.

Watch mode runs while its process is open. It does not install a system service or configure startup. Restart it after a reboot. If a refresh fails, the previous HTML stays available and the process retries on the next interval. To update the code, run `git pull --ff-only`, then restart the script.

## Quick usage without a dashboard

```sh
python3 agent_usage.py usage
```

Example output:

```text
For Aug 30–Sep 5: $1,327.32 estimated API cost. In: 29M, Out: 1.28M
```

The command reads local traces, reuses the parse cache, prints the last seven days, and includes a comparison with the previous seven days when records exist. It generates no HTML, opens no browser and starts no server. These example numbers are illustrative; your report uses this device's actual recorded usage.

`In` is total input tokens, including cache reads and writes; `Out` is output tokens. Counts use K/M/B/T with up to two decimal places. The comparison covers estimated cost, input and output. JSON retains exact token counts, requests and sessions for detailed analysis.

Use JSON for scripts and agent analysis:

```sh
python3 agent_usage.py usage --json
python3 agent_usage.py usage --json --provider claude --days 30
python3 agent_usage.py usage --json --from 2026-08-30 --to 2026-09-05 --model gpt-6-astra
python3 agent_usage.py usage --json --all-time --include-requests
```

`--provider` accepts Codex/OpenAI or Claude/Anthropic, case-insensitively. `--model`, `--project` and `--role main|subagent|review` filter both periods. `--from` and `--to` are inclusive report-timezone dates. `--days` defaults to 7; `--to` can anchor a historical window. `--all-time` includes all observed dates with no comparison. Existing source, pricing, timezone and output options work with `usage` too.

`--json` writes one JSON object to stdout. Every usage run also saves `output/usage-report.json`; full normalized evidence remains in `output/usage.json`.

| JSON field | Contents |
| --- | --- |
| `schema_version`, `version` | Report schema and AISAD release versions |
| `period`, `previous_period`, `filters`, `timezone` | Exact scope of the report |
| `current.totals`, `previous.totals` | Requests, distinct sessions, tokens, weighted cache share, pricing coverage and cost components |
| `current.by_provider`, `by_model`, `by_project`, `by_role`, `by_session`, `by_date` | Breakdowns; also present under `previous` |
| `current.rows`, `previous.rows` | Joint date/provider/model/session/project/role groups for custom analysis |
| `current.requests`, `previous.requests` | Optional normalized request records with `--include-requests`; no transcripts |
| `changes` | Comparison status and deltas; missing data and uncertain prices remain explicit |
| `quality`, `scan`, `source_summary` | Collection diagnostics over all discovered history, not just the filtered period |
| `price_as_of`, `price_sources`, `unknown_models` | Price provenance and unpriced models in the current filtered period |
| `current.telemetry`, `previous.telemetry` | Trace coverage and measured tool/MCP counts and sizes |
| `current.request_stats`, `previous.request_stats` | Per-request context, timing and numeric trace statistics with `--include-requests` |
| `pools`, `pool_scope` | Shared interactive and managed spend across all providers/projects for the selected dates |

`estimated_cost_usd` and `estimated_cost_high_usd` are null when no requests can be priced. With partial pricing they contain the known subtotal; check `unpriced_requests` before interpreting them as a complete total. `known_cost_usd` always names that known subtotal explicitly. A nonzero range reflects unknown cache TTLs. `cache_share` is a fraction; its delta uses percentage points. Session counts are distinct within each group, so adding sessions across models or dates double-counts shared sessions. Missing dates are absent from the breakdown, not proof of zero usage.

## Session statistics

Use `usage --json --include-requests` to inspect request timing, input/output tokens, cache usage, and numeric tool/MCP counts and sizes. These records support questions such as “Which sessions had the largest tool payloads?” or “How did cache usage change this week?” Tool bytes are measured locally and are not converted into billed tokens. Missing tool telemetry is reported explicitly.

`analyze` remains an alias for `usage`, including JSON and filters. It returns statistics only. AISAD does not generate recommendations, flag workflow patterns, or estimate hypothetical savings.

Usage and status-line JSON now use `schema_version: 2`. Usage reports replace `diagnostics` with `telemetry` and `analysis_records` with `request_stats`; `analysis_rules` is removed. Status-line reports omit coaching fields. Token and cost totals, breakdowns, periods and comparisons keep their existing field names. The full `usage.json` snapshot exposes numeric request statistics in `request_stats`.

## Live terminal status line

```sh
python3 agent_usage.py statusline
python3 agent_usage.py statusline --watch 5 --budget 500
python3 agent_usage.py statusline --json --session Codex:SESSION_ID
```

The line shows the recorded session lifetime estimate, provider spend for the selected period, the shared interactive pool, and context/cache counters. `--session` selects a session; otherwise AISAD uses `CODEX_THREAD_ID` when present or clearly labels the latest observed session. This is local trace telemetry, so the counter updates when the harness writes usage records. `--watch` runs in the terminal without HTTP or HTML; press `Ctrl+C` to stop. `--json --watch 5` emits NDJSON, one object per change.

`--budget USD` sets expected spend for the selected period across all local interactive harnesses. The counter marks the 50/80/100% thresholds of that amount. Provider/model/project/role filters never reduce this shared pool. `--managed-budget USD` sets a separate budget, and repeated `--managed-session PROVIDER:ID` options tag managed roots and their confirmed descendants. Ordinary subagents remain in the interactive pool. `--pool managed` or `--pool interactive` filters statistics.

Budgets are optional CLI inputs, not enforced limits or inferred subscription allowances. The same amount applies to whichever period you select. There are no Slack notifications, approval flows, remote collection, or automatic model changes.

### Claude Code status-line integration

After installing the skill for Claude Code, merge this entry into `~/.claude/settings.json`, preserving your other settings. Replace the helper path if your installation differs:

```json
{
  "statusLine": {
    "type": "command",
    "command": "python3 \"$HOME/.claude/skills/aisad/scripts/aisad.py\" statusline --offline --stdin",
    "refreshInterval": 5
  }
}
```

Claude supplies its `session_id` as JSON on stdin. Add `--budget 500` to the command only if that is your chosen period budget. `--offline` skips update checks in this frequent hook. See [Claude Code's status-line documentation](https://code.claude.com/docs/en/statusline). For Codex, run the terminal command alongside your session; AISAD does not modify Codex's native footer.

## Install the skill

From a clone of this repository:

```sh
python3 skills/aisad/scripts/aisad.py install --target codex
```

Use `--target claude` for Claude Code or `--target both` for both applications. Defaults are `~/.codex/skills/aisad` and `~/.claude/skills/aisad`, honoring `CODEX_HOME` and `CLAUDE_CONFIG_DIR`. Use `--dest '/path/to/skills'` for a custom skills parent directory, or `--version 1.0.1` to install that published release. The package includes its own collector; you do not need to keep the clone afterward.

You can also ask Codex's skill installer to install `skills/aisad` from `aiatsuk/aisad`. A raw GitHub skill installation downloads its bundled runtime on first use. A release installation already includes the runtime and works offline immediately.

In a new turn, invoke `$aisad usage` in Codex or `/aisad usage` in Claude Code. Ask follow-up questions such as:

- “Which models cost the most this week?”
- “Compare Claude and Codex with the previous week.”
- “Which sessions explain the increase in estimated cost?”
- “Show cache usage for this project over the last 30 days.”
- “Show the largest recorded context and tool payloads by session.”
- “Show a live shared spend counter for Claude and Codex.”

The skill collects JSON and computes answers locally. It uses the text command for a quick summary and opens the dashboard when requested. Its instructions are in [skills/aisad/SKILL.md](skills/aisad/SKILL.md).

### Updates and offline use

The installed helper supports:

```sh
python3 ~/.codex/skills/aisad/scripts/aisad.py version
python3 ~/.codex/skills/aisad/scripts/aisad.py check-update
python3 ~/.codex/skills/aisad/scripts/aisad.py update
python3 ~/.codex/skills/aisad/scripts/aisad.py usage --json
python3 ~/.codex/skills/aisad/scripts/aisad.py usage --offline
python3 ~/.codex/skills/aisad/scripts/aisad.py analyze --json
python3 ~/.codex/skills/aisad/scripts/aisad.py statusline --offline --watch 5
python3 ~/.codex/skills/aisad/scripts/aisad.py run -- --watch 60 --open
```

Substitute your installed skill directory if it differs. `usage`, `analyze`, `statusline` and `run` check for a newer stable release at most once every 24 hours when invoked. They update the skill, launcher and collector together before running. Update messages go to stderr, keeping JSON stdout clean. `check-update` checks immediately without replacing code; `update` applies a newer release immediately. Running dashboard processes retain their loaded code until restarted.

Checks and downloads contact only the public GitHub repository for release metadata and code. They transmit no traces, metrics or device identifiers. `--offline` skips those requests. Set `AISAD_AUTO_UPDATE=0` to disable automatic checks persistently in your environment; explicit `check-update` and `update` still work. If an automatic check fails, the installed version remains usable. No scheduler or startup service is installed.

Skill reports default to `~/.local/share/aisad/output`, outside the replaceable installation. `AISAD_DATA_DIR` or the helper's `--data-dir` selects another local data directory. Collector arguments can follow `--`; keep custom outputs outside the skill directory. Updates verify SHA-256 checksums and the package manifest, preserve local modifications by refusing to overwrite them, and restore the previous installation if replacement fails.

For offline installation, download the skill ZIP and `SHA256SUMS` from a [release](https://github.com/aiatsuk/aisad/releases), then use a local copy of the helper:

```sh
python3 skills/aisad/scripts/aisad.py install \
  --archive aisad-skill-v1.0.1.zip --checksum-file SHA256SUMS --target codex
```

### Move an existing 2.x installation to 1.0.0

The earlier 2.x numbers were assigned during implementation. Stable versioning now starts at **1.0.0**. Existing installations need a one-time reinstall because their updater correctly refuses a lower version number.

Run the helper from an updated repository clone:

```sh
git pull --ff-only
python3 skills/aisad/scripts/aisad.py install --target codex --version 1.0.0 --allow-downgrade
```

Use `--target claude` or `--target both` as appropriate. Reports remain in the data directory, and local edits are still protected. After this transition, automatic updates follow the normal 1.0.1, 1.1.0, and later release sequence. The downgrade option is available only for an explicit installation; automatic updates never downgrade.

## What you can explore

- The last seven days by default, compared with the preceding seven days when records exist.
- Provider totals for OpenAI/Codex and Anthropic/Claude; click a provider to filter the dashboard.
- Tokens and estimated cost by model, day, project and session.
- Uncached input, output, cache reads and 5-minute/1-hour cache writes.
- Main threads, subagents and auto-review where roles are recorded.
- Global period, date, provider, model, project, role and pool filters; a searchable, sortable session table with request timelines.
- Context and tool/MCP footprints, cache usage, shared spend pools and optional budget counters.
- Trace coverage, parsing diagnostics and requests with unknown prices.

Session titles are excluded by default; the dashboard uses session IDs and project names. `--include-titles` adds shortened titles with basic redaction of obvious secrets. This is not comprehensive anonymization. Message bodies, reasoning, tool arguments and tool results are not saved in the export.

## Periods and comparisons

The default **Last 7 days** includes the snapshot date and the six preceding calendar days, using the report's timezone. For example, a September 5 snapshot shows August 30–September 5 against August 23–29. An old trace does not move the window backward. Watch mode refreshes at local midnight even when source files have not changed.

Choose **This week (Mon–today)** for the current calendar week so far, compared with the same weekdays last week. **Last week (Mon–Sun)** shows the previous complete calendar week, compared with the calendar week before it. Both use the snapshot date in the report's timezone.

You can also choose **Last 30 days**, **All time**, or enter a custom date range. Rolling and custom ranges are compared with the immediately preceding range of equal length. All time has no comparison, and Reset restores the last seven days with all providers selected.

Summary cards show percentage changes and previous values; cache rates show changes in percentage points. The daily chart aligns the previous period by day, with actual dates available on hover. Provider, model, project, role and pool filters apply to both periods. Search only affects the sessions table.

Comparisons use recorded observations, not guaranteed complete coverage. The current day is partial. Missing previous-period records are labeled explicitly, and missing current records do not produce a false 100% decrease. A zero baseline has no percentage change. Cost totals and deltas use known priced requests in each period. Unpriced requests are excluded from monetary comparisons and disclosed separately; request and token counts retain all observations. No priced observations means unavailable cost, not zero. Price ranges still suppress a single percentage delta.

## How cost is estimated

**Local token counts cannot reveal subscription charges, remaining account limits or a provider invoice.** Even Claude SDK `total_cost_usd` is an estimate. AISAD does not add it to request-level costs because it may already include subagents and cumulative totals across turns.

Built-in rates calculate an **API-equivalent estimate** from each model's input, output, cache usage and available processing mode/geography. The catalog was checked on **September 5, 2026**. It is a current-rate scenario applied to the available history, not a reconstructed billing history.

Missing tiers default to Standard and missing geography defaults to global. An unknown model or unsupported mode has a missing price, not a zero price; the request is excluded from the displayed cost subtotal and comparison, with its count disclosed separately. If a Claude cache-write TTL is unknown, cost is shown as a 5-minute to 1-hour range.

The dashboard explains partial pricing in **Excluded from cost**, with counts, tokens and reasons for the selected filters. `current.pricing_coverage` and `previous.pricing_coverage` expose the same grouping in usage JSON. Internal `codex-auto-review` observations remain counted but unpriced until a verified rate is provided; they are never silently treated as free.

## Local pricing overrides

Create and edit a local price catalog:

```sh
python3 agent_usage.py --write-prices prices.json
python3 agent_usage.py --prices prices.json --open
```

`models` maps model IDs to `input`, `cached`, `write_5m`, `write_1h` and `output` rates in USD per million tokens. To describe historical prices, replace a model's rate object with a list of objects using `valid_from` (inclusive) and `valid_to` (exclusive). Zero or multiple matching rules leave the price unknown.

Supported adjustments include `long_threshold`, `long_input_multiplier`, `long_output_multiplier`, `long_scope` (`session`, or per request by default), `fast_multiplier`, `flex_multiplier` and `batch_multiplier`. `as_of` records when the catalog was checked. The collector never fetches prices. A new AISAD release may include an updated built-in catalog; a local `--prices` file continues to override it.

Explicitly recorded server-side web searches are included at $0.01 per search. Other service fees, discounts, taxes and missing telemetry are not reconstructed. Output counts come from traces, which can contain intermediate SDK values; estimates reflect only the recorded observations.

Sources: [OpenAI pricing](https://developers.openai.com/api/docs/pricing), [Claude pricing](https://platform.claude.com/docs/en/about-claude/pricing), [Claude SDK cost tracking](https://code.claude.com/docs/en/agent-sdk/cost-tracking).

## Local data sources

- **Codex:** `$CODEX_HOME` or `~/.codex`; `sessions`, `archived_sessions` and the newest readable `state_*.sqlite` registry.
- **Claude Code:** `$CLAUDE_CONFIG_DIR` or `~/.claude`; `projects`, including nested `subagents`.
- **Optional `--cowork`:** local Claude Cowork audit traces under macOS Application Support.

Override the directories when needed:

```sh
python3 agent_usage.py --codex-dir '/local/path/Codex' --claude-dir '/local/path/Claude' --output '/local/path/Report'
```

`--home '/path/to/profile'` selects another local profile. In this mode, `CODEX_HOME` and `CLAUDE_CONFIG_DIR` are ignored unless explicit source directories are supplied. The timezone defaults to the system setting. Use `--timezone Europe/Amsterdam` to override it; this requires an installed IANA timezone database, available on standard macOS systems.

Source SQLite databases are opened read-only. The parser handles incomplete final JSONL records, cumulative counter resets and missing directories. Changed files are reread; unchanged files use a local cache. Removed source files disappear from subsequent snapshots and are removed from the cache. Duplicate messages across files are counted once; copied Claude requests are assigned to the first main trace in a stable order.

## Output and privacy

`output/` contains:

| File | Purpose |
| --- | --- |
| `dashboard.html` | Self-contained offline dashboard |
| `usage.json` | Normalized usage evidence and local source metadata |
| `usage-report.json` | Filtered text/JSON command report, written by headless commands |
| `statusline.json` | Session/provider/pool and context/cache counters from `statusline` |
| `parse-cache.sqlite` | Local cache of parsed files |
| `prices-used.json` | Price catalog used for the snapshot |
| `status.json` | Snapshot timestamp for automatic refresh |

The local server exposes only the dashboard and its update timestamp. Raw exports and the parse cache are not served.

**Clone the code on each device; keep its reports local.** Default output, JSONL traces, databases, local data exports and price overrides are excluded through `.gitignore`. If you use a custom `--output` directory, place it outside the repository or add it to your local Git exclusions. Reports still contain session and project metadata; publishing them is not required to use AISAD.

`refresh.py` is an alternative entry point with the same behavior.

## Versions and releases

`python3 agent_usage.py --version` prints the installed collector version. AISAD uses semantic release versions. The JSON contracts are versioned separately with `schema_version`; incompatible report changes increment that field. Scripts consuming JSON should check it before reading the report.

**1.0.0 is the stable baseline.** Earlier 2.x tags remain available as historical artifacts. GitHub's Latest release is the update source, and the release workflow explicitly marks the new release as Latest.

`VERSION` in `agent_usage.py` is the source of truth. Release tags use `vX.Y.Z` and must match it. See [CHANGELOG.md](CHANGELOG.md) for changes and [GitHub Releases](https://github.com/aiatsuk/aisad/releases) for published assets:

- `agent_usage.py`: standalone collector and dashboard.
- `aisad-skill-vX.Y.Z.zip`: skill instructions, helper, bundled collector and file manifest.
- `SHA256SUMS`: checksums for both downloads.

For maintainers, update `VERSION` and the changelog, then test and build:

```sh
python3 -m unittest discover -v
python3 scripts/build_release.py --tag v1.0.1
```

The builder uses an explicit source-file list and deterministic ZIP metadata. Local reports, caches and session history are never included. Push the matching tag after the code is committed; the release workflow runs the cross-platform and browser suites before publishing the assets. Stable releases are the skill updater's source; it does not install arbitrary branch changes or prereleases.

## Tests and demo

```sh
python3 -m unittest discover -v
```

Tests use synthetic profiles only. They cover parsing, pricing, weekly JSON/text reports, filters, missing data, offline operation, release integrity, installation, updates, rollback, preservation of local edits, paths with spaces and loopback refresh. GitHub Actions runs the suite on macOS, Linux and Windows without collecting any personal history.

To generate the example dashboard without reading your sessions:

```sh
python3 scripts/make_demo.py
```

Open `output/demo/dashboard.html` in a browser. The demo is deterministic and uses synthetic sessions. The README screenshot was captured from this page. Playwright is needed only if you choose to recreate the screenshot with `scripts/capture_demo.cjs`; it is not a dashboard dependency.

Optional browser regression checks and screenshot generation:

```sh
npm install --no-save --package-lock=false playwright@1.62.1
npx --no-install playwright install chromium
python3 scripts/make_demo.py
node scripts/test_dashboard.cjs
node scripts/capture_demo.cjs
```

These checks exercise calendar boundaries, comparison arithmetic, provider filters, missing history, price uncertainty and mobile rendering using synthetic data only. GitHub Actions runs them in addition to the Python tests.

## Background and limits

Inspired by Visibility & Education and figures 11–12 in [Uber: The Efficient Software Factory](https://www.uber.com/by/en/blog/efficient-software-factory/). Token counts do not establish productivity, output quality or time saved.

The dashboard follows [Uber Base](https://base.uber.com/6d2425e9f/p/294ab4-base-design-system) conventions using the public [Base Web colors](https://baseweb.design/guides/colors/) and [theme guidance](https://baseweb.design/guides/theming/): neutral surfaces, black primary controls, clear type, and semantic status colors. It includes a dark theme and keyboard navigation. The implementation stays dependency-free, with system fonts and no remote assets; it does not bundle proprietary Uber fonts or require access to private design-system pages.

Forked Codex traces can contain copied parent usage with rewritten timestamps. AISAD excludes that prefix when the first local turn context establishes the fork boundary, then keeps subsequent usage under the child session. Files without a turn context retain their uncertain records and are counted in `quality.codex_fork_without_turn_context`.

Supported sources are local **Claude Code and Codex** traces, not all cloud conversations in Claude.ai or ChatGPT. Deleted or unsaved sessions cannot be recovered. Log format changes may require parser updates; diagnostics expose missing data and unknown models.

### Current-price estimates and history coverage

The default catalog applies current published prices to all recorded dates, so it estimates what the observed usage would cost at those rates. It is not historical billing or subscription spend. `history_coverage` reports the first/last observed dates by provider; missing registered Codex traces are counted in `quality.registry_without_trace`.

Local Grok Build `updates.jsonl` completed-turn summaries appear separately in `grok_usage` and a collapsed dashboard row. They retain provider-reported cost ticks (USD = ticks / 10^10), model-call counts, and incomplete-usage flags. They are not added to the Claude/Codex current-price estimate: turn totals do not provide the per-request context needed for reliable repricing. See [xAI cost tracking](https://docs.x.ai/developers/cost-tracking).
