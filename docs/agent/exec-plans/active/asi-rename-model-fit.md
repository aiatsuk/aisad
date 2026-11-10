# Rename to ASI and add model fit

- Status: in progress
- Source: User request, 2026-11-10 (rename aisad to asi everywhere; merge the model and effort advisor into it, including the dashboard; commands `/asi-suggest`, `/asi-analyze`, `/asi-autopilot`, `/asi-ultraanalyze`)
- Last updated: 2026-11-10
- Branch: `feat/asi-model-fit`, worktree `~/pr/asi-wt`, cut from `origin/main` 07ce453 (1.5.2)
- Prototype to port from: `~/pr/air` (commit 0622eea): `airlib/guide.py`, `airlib/analyze.py`, `airlib/transcripts.py`, `airlib/rules.py`, `airlib/dashboard.html`, `skills/*/SKILL.md`, `tests/test_air.py` (43 tests). It is tested logic; port behaviour and tests, not file layout.

## Goal

One tool named ASI. It keeps everything aisad 1.5.2 does and adds model fit: for every main-thread turn and subagent run of Claude Code, compare the model and effort that ran with what Anthropic's guide "Which Claude model should you build with?" (claude.dev, 2026-11-09) suggests, in the CLI, the HTML dashboard and four skills.

## Steps (one commit each; tick when the commit exists and its checks pass)

- [x] 1. Rename aisad to asi with compatibility (section "Rename").
- [x] 2. Model fit engine and `fit` / `suggest` commands in `agent_usage.py`, with tests (section "Model fit engine").
- [x] 3. "Model fit" tab in the HTML dashboard, with browser tests (section "Dashboard").
- [x] 4. Rules block and autopilot in the launcher, four sub-skills, installer links, docs (ADR 0005, README, SKILL.md, CHANGELOG 2.0.0, VERSION 2.0.0).
- [ ] 5. Terminal (Ink) view: moved to a follow-up (the Ink UI is only the monthly spend chart; a model-fit view there is its own piece of work). The PR says so.
- [ ] 6. Error-path review, independent review, fixes, PR. No merge, no GitHub repo rename, no install before the owner says so.

## Rename

New names: tool `asi`, display name `ASI`; repo `aiatsuk/asi` (the GitHub rename itself happens at release, not in this branch); skill dir `skills/asi`; launcher `skills/asi/scripts/asi.py`; CLI launcher `asi`; release zip `asi-skill-vX.Y.Z.zip` with root `asi/`; manifest `repository: aiatsuk/asi`; UI bundle `asi-ui.mjs`; Swift package, targets and dirs `ASIMenuBar`, `ASICore`, `ASICoreTests` (use `git mv`); app `ASIMenuBar.app`, display name `ASI`; bundle id and log subsystem `com.aiatsuk.asi.menubar`; env vars `ASI_*`; data dir `~/.local/share/asi`; live globals `asiLiveRevision` / `asiLiveData`; localStorage `asi-theme`; user agents, thread names, temp prefixes, texts.

Compatibility (each needs a test):
- Env vars: read `ASI_X` first, then `AISAD_X` (Python launcher, collector, Swift). One helper per language.
- Data dir: when `ASI_DATA_DIR`/`AISAD_DATA_DIR` are unset and `~/.local/share/asi` does not exist but `~/.local/share/aisad` does, the Python launcher moves the old dir to the new path once (rename; on failure keep using the old dir and say so on stderr). The Swift app never moves anything: it uses the new dir if it exists, else the old dir if it exists, else the new dir.
- Shared live files: the reader of `usage-live.js` accepts both the old and new global names; the writer writes the new one. Dashboard JS and Swift `SharedUsageReader` change together with the writer.
- localStorage: read `asi-theme`, fall back to `aisad-theme`.
- `install` (launcher): installs to `skills/asi`. If `skills/aisad` exists next to it and is an unmodified managed install (its manifest verifies), remove it; if it has local changes, leave it and print one line. `--cli-dir`: write the `asi` launcher; if an `aisad` launcher with the `# AISAD CLI launcher` marker exists there, replace its body with one that execs the new launcher (alias).
- `launch_menubar`: look for `ASI.app`, `ASIMenuBar.app`, then the old names; `open -b` the new bundle id, then the old.
- No bridge release: 1.x installs validate `repository == aiatsuk/aisad`, the `aisad/` zip root and the `aisad-skill-v` asset name, so they cannot auto-update to 2.0.0. They keep working at 1.5.2; the changelog tells the user to run the 2.0.0 installer once.

Do not rename: CHANGELOG history, `docs/agent/exec-plans/completed/*`, `docs/agent/reports/*`, old-artifact examples in README that name a 1.x file. Add new text instead.

Checks for step 1: `python3 -m unittest discover -q` (196 before the change, baseline OK); `swift test --package-path macos` and `./script/build_and_run.sh --build-only`; in `ui/`: `bun install --frozen-lockfile --ignore-scripts && bun run check && bun run test && bun run build && python3 test/pty_motion.py && python3 test/pty_first_frame.py && python3 test/pty_live.py && python3 test/pty_shared.py`; `python3 scripts/make_demo.py && python3 scripts/build_release.py --with-ui`; browser scripts (`node scripts/test_*.cjs`, need playwright; report honestly if it cannot run here); `git grep -i aisad` leaves only the allowed places (history, compatibility fallbacks and their tests).

## Model fit engine (step 2)

Everything lives in `agent_usage.py` (single-file runtime: the release ships it alone, the menu bar app bundles it). Add a clearly marked section; keep the file's Python 3.9 compatibility.

Capture in `parse_claude` (bump `PARSER_VERSION`), without changing existing row fields or session ids:
- per request `fit`: human-turn index, number of tool calls, edited files as `[short hash, is_document]` pairs (never the path), Agent/Task spawn count and `{tool_use_id: model}` for spawns that passed a model, workflow flag, web call count, screen/browser action count;
- per session `fit`: for subagent files the sibling `agent-<id>.meta.json` reduced to `agent_type`, `explicit_model`, flags `relay` / `review` / `plan` computed from type, description and phase (the description text itself only when titles are included); the real parent session id taken from the path component before `subagents` (workflow agents today get parent `Claude:workflows`; do not change that field, add the correct one); per human turn: timestamp, flags `big` / `hard` from the prompt keywords, and the redacted title only with `--include-titles`.
- Human turn = a typed prompt as in the prototype's `_human_text` (not tool results, meta, compact summaries, harness blocks, non-human origin).
- Record shapes are untrusted: a bad record costs one record, counted in `quality`, never the session (prototype test `test_odd_record_shapes_cost_one_record_not_the_session`).

Units and verdicts (port `guide.CLASSES`, `classify`, `session_tier`, `judge`, events and `summarize` from the prototype):
- unit = one human turn of a main thread, or one subagent run; cost = the collector's own priced cost of its requests (unpriced requests counted, not guessed);
- alternative cost on each current tier (haiku, sonnet, opus, fable) = the same requests repriced through the collector's price rules, so there is one price table;
- main threads judged per session (`session_tier`), subagents per run, effort per unit; verdicts `over`, `under`, `effort-over`, `effort-under`, `session`, `fits`; savings as in the prototype (effort ratios low 0.33, medium 0.70, high 1.0, xhigh 2.5, max 2.5);
- events from ordered main-thread requests: model switches (cache re-write cost), full cache rewrites after an idle gap over 5 minutes (not after compaction), calls above 200k context per day, Haiku calls above 100k, fast-mode calls, effort changes with the cache-read share of the next call.

Commands:
- `fit` with the usual period flags (`--days`, `--from`, `--to`, `--all-time`) prints the period summary; `fit --session <id or unique prefix>` prints the turn-by-turn view; `--json` for both; prompt titles only with `--include-titles`. An ambiguous prefix, an unknown session, a session without model calls and an empty period are clear errors with a non-zero exit, no traceback.
- `suggest [--session <id>]`: current model, effort, context size, per-call cache-read cost, one-time switch cost per tier, defaults from `settings.json` (malformed shapes ignored), recent turns with heuristic classes, and the guide table text.
- Snapshot: `make_snapshot` adds `model_fit` for the dashboard: `{guide, units, events, note}` where `units` are compact per-unit records already judged in Python (kind, session, project, date, used tier, effort, class, signals, recommended tier and efforts, verdict, cost, save_model, save_effort, calls, agent_type, explicit_model, title only with titles) and `events` are the switch / cold-rewrite / per-day lists. The dashboard only filters and sums; no judging logic in JS.

Privacy (existing repo rule): no source paths, transcripts or tool payloads in HTML or UI datasets; prompt text only as the existing opt-in redacted title.

As built (step 2), where it differs from or adds to the text above:
- Per-request facts are one dict per reply, shared by every usage block of that reply in a file, so tool calls split across blocks are all counted (deduplicated by tool-use ID). `merge_requests` keeps the owner's turn index and the union of tool calls when a reply is copied into another session. `make_snapshot` pops the facts off the rows right after pricing, so rows, `request_stats`, `usage.json`, `sessions.sqlite` and `usage --include-requests` keep their old shape (tested against a run with the capture switched off).
- Subagent keyword flags `big` / `hard` come from the run's first typed prompt plus its description, as in the prototype's classifier; the prompt itself is not kept.
- Cowork `audit.jsonl` traces are not read for model fit (Claude Code only); Codex is out of scope.
- `parse_claude` now guards every record: an unexpected shape is counted in `quality.invalid_records` (malformed `cache_creation` in `invalid_usage`) instead of failing the whole file, as the plan's record rule asks. Before, a non-object `cache_creation` or `server_tool_use`, an unhashable tool ID, or odd user content with `--include-titles` lost the file.
- Malformed `agent-<id>.meta.json` files are counted in `quality.fit_unreadable_meta`; a missing one is normal.
- Alternatives reprice each priced request on the tier's current model with `_price_request` at standard speed (fast and priority mode dropped, batch kept), only for units judged `over`. A unit's saving is 0 when the tier's model has no price in the catalog.
- `fit` writes `fit-report.json` next to the other reports. `fit --session` shows the whole session (all dates); the period flags apply to the summary view. `suggest` picks `--session`, else `CLAUDE_SESSION_ID`, else the newest session whose project folder matches the current directory (matched by a hash of the encoded folder name, never stored as a path). Rules/autopilot status is not part of `suggest` yet (step 4).

## Snapshot contract (for step 3)

`make_snapshot` adds `model_fit`; the same object is in the shared live snapshot (`publish_shared_usage` whitelist), because open dashboards replace their whole dataset `D` with the shared one on a live update (`applyLiveSnapshot`) and the tab would otherwise go empty. Costs are USD floats rounded to 4 decimals; `ts` is epoch seconds (integer). All dates and all units are included; the page filters by period like it does for `rows`.

- `schema`: `1`.
- `guide`: one entry per class, in table order: `class` (id), `label`, `tier` (`haiku` | `sonnet` | `opus` | `fable`), `effort` (where to start), `effort_max` (highest effort before moving up a model), `why`.
- `units`: every main-thread turn and subagent run of Claude Code, sorted by `ts`. Every key is present on every unit:
  - `kind`: `turn` | `agent`. For the existing role filter: `turn` is role `main`, `agent` is role `subagent`.
  - `session`: the same value as `rows[].session` (`Claude:<id>`; subagents `Claude:<id>/agent-<x>`; workflow agents keep the rows' `Claude:workflows/agent-<x>`).
  - `main_session`: the main session the unit belongs to (`Claude:<id>`): equal to `session` for turns, the real parent for every subagent, workflow agents included. Group by it for "most expensive sessions".
  - `n`: human-turn number in the main thread (1 = first typed prompt; 0 = calls before the first prompt, for example a resumed session); `null` for agents.
  - `project`, `date`: the same values as `rows` (from the unit's first request; date in the report timezone).
  - `ts`: start of the unit (its first request).
  - `tier`: tier of the model that carried most of the cost, derived from its canonical ID, `null` when it is none of the four tiers; `model`: that model ID as recorded, the same form as `rows[].model` (a dated ID such as `claude-haiku-4-5-20251001` stays dated), so the dashboard's model filter, whose options come from `rows`, finds the unit. When one model was recorded under several IDs, the ID that carried most of its cost.
  - `effort`: effort that carried most of the cost: `low` | `medium` | `high` | `xhigh` | `max` | `unknown` (or another recorded string).
  - `class`, `signals`: heuristic class ID (a `guide[].class`) and the short reason (`"12 calls, no edits"`).
  - `rec_tier`, `rec_effort`, `rec_effort_max`: the guide's recommendation for that class.
  - `verdict`: `over` | `under` | `effort-over` | `effort-under` | `session` | `fits`.
  - `effort_over`: boolean, effort above `rec_effort_max`.
  - `cost`: priced cost of the unit's requests; `unpriced`: number of its requests without a price (left out of `cost` and both savings).
  - `save_model`, `save_effort`: rough savings at the guide's model and effort (upper bounds); never negative, and together never more than `cost`. A unit is `over` only when the guide's model is cheaper for its requests (or has no price, saving 0); when it costs as much or more (Haiku above its long-prompt threshold can), the unit is judged on effort alone.
  - `calls`: number of requests.
  - `agent_type`: subagent type from the meta sidecar (`unknown` without one); `null` for turns.
  - `explicit_model`: subagents: a model was passed on the spawn or set in the meta; `null` for turns.
  - `title`: only with `--include-titles`: the redacted prompt (turns) or description (agents), or `null`. Absent otherwise.
- `events`: main-thread calls only (subagent calls are not events):
  - `switches[]`: `session`, `project`, `date`, `ts`, `from`, `to` (model IDs as recorded, the same form as `rows[].model`; models are compared by canonical ID, so a dated and an undated ID of one model are no switch), `tokens` (cache tokens written), `cost` (cache-write cost; `null` when unpriced).
  - `cold[]`: `session`, `project`, `date`, `ts`, `gap_min`, `model` (as recorded), `tokens`, `cost` (full cache rewrite after an idle gap over 5 minutes, not after compaction).
  - `effort_changes[]`: `session`, `project`, `date`, `ts`, `from`, `to`, `read_share` (cache-read share of the call after the change).
  - `daily[]`: one entry per `date` and `project`: `calls`, `cost`, `big_calls`, `big_cost` (context over 200k), `haiku_long_calls`, `haiku_long_cost` (Haiku over 100k), `fast_calls`, `fast_cost`.
- `note`: caveat text to show with the tab.

The page only filters and sums. The findings of `fit` map to unit filters: model-over = `verdict == 'over'` (sum `save_model`); effort-over = `effort_over` (sum `save_effort`); agent-inherit = `kind == 'agent' && !explicit_model && verdict == 'over'`; model-under = `verdict == 'under' && cost >= 0.05`; Opus at xhigh or max = `tier == 'opus' && effort in (xhigh, max)`; switches, cold cache, big context, Haiku long prompts and fast mode come from `events` (the effort-change finding needs at least 5 changes). Examples are the largest units of each filter.

## Dashboard (step 3)

Fifth tab "Model fit" in the `HTML` string of `agent_usage.py`, following the page's existing tokens, filters (period, project, role), light and dark themes and hand-rolled SVG/CSS charts. Content, ported from the prototype page: four tiles (spend in view, share run by subagents, spend on a bigger model than the guide suggests with its saving, rough saving from effort), spend per day stacked by model tier, spend by task class with the two savings, class by model matrix with the guide's cell outlined, spend by effort, findings with their largest examples, most expensive sessions. Text set with `textContent` only. Update the tab-count assertion and add browser checks for the new tab (render, empty state, filter change, no console errors, phone width without horizontal scroll).

## Sub-skills and rules (step 4)

- Launcher commands `rules on|off|status|show` and `autopilot on|off|status|show` manage one marked block (`<!-- asi:begin -->` to `<!-- asi:end -->`) in `<CLAUDE_CONFIG_DIR or ~/.claude>/CLAUDE.md`; state in the data dir. Port `rules.py` with all its tests (CRLF, symlink, reversed markers, non-UTF-8, state/file rollback, new-file mode 0644). On first run, an existing `<!-- air:begin -->` block from the prototype is replaced, not duplicated.
- Sub-skills live inside the managed skill: `skills/asi/subskills/asi-suggest|asi-analyze|asi-autopilot|asi-ultraanalyze/SKILL.md`, covered by the manifest. `install` for the Claude host links each as `skills/<name> -> asi/subskills/<name>` (refuse to replace anything that is not such a link). They call `python3 "${CLAUDE_SKILL_DIR}/../../scripts/asi.py" ...` (verified 2026-11-10 on CLI 2.1.321: `${CLAUDE_SKILL_DIR}` and `${CLAUDE_SESSION_ID}` are substituted, and symlinked skills work). No `model` or `effort` in their frontmatter: a one-turn switch would re-write the session's cache.
- ADR 0005 replaces the "no routing suggestions" part of ADR 0002 for model fit and says why (owner request; the guide gives a public reference; savings are labelled as upper bounds).

## Decisions

- Version 2.0.0 (the rename breaks installed 1.x updaters).
- Savings are upper bounds on API-equivalent estimates; the guide is a starting point and the owner's own measurements win (for example reviewers kept on a stronger model after the 2026-10-24 A/B).
- The first-message hint and autopilot are instructions in `CLAUDE.md`, no hooks.

## Log

- 2026-11-10: plan written; baseline `python3 -m unittest discover -q`: 196 tests OK. No open PRs on the repo (PR #27 already merged as 1.5.2). Local branch `feat/usage-forecast` (menu bar forecast, one commit, not a PR) is NOT part of this work and will conflict with the Swift rename when it is rebased.
- 2026-11-10: step 1 done. Checks: `python3 -m unittest discover -q` 215 OK (also the 64 changed-file tests on Python 3.9.6; the baseline's one error was a race in `test_r_in_the_ui_requests_one_background_collection`, now joined safely); `swift test --package-path macos` 74 tests, 0 failures; `./script/build_and_run.sh --build-only` built `dist/ASIMenuBar.app` (`com.aiatsuk.asi.menubar`); `ui/`: frozen install, `tsc`, 51 bun tests, build and the four PTY scripts pass on local bun 1.4.0; `make_demo.py` and `build_release.py --with-ui` build `asi-skill-v1.5.2.zip`; the six browser scripts pass with playwright 1.62.1 installed without saving. Not done here: the binary GIFs in `docs/` were not re-recorded and may still show the old name; the menu bar app's saved chart range and its menu bar permission do not carry over to the new bundle ID. Incident: one test run (an existing `version` subprocess with the real home) moved the real `~/.local/share/aisad` to `~/.local/share/asi` at 08:24; it was moved back unchanged at 08:35, and `test_skill.py` now runs every test with a temporary `HOME`.
- 2026-11-10: step 2 done (model fit engine, `fit` / `suggest`, `model_fit` in the snapshot and the shared live snapshot; `PARSER_VERSION` 10, so the first run after an update reparses every trace once: 2 min 7 s cold for the owner's full history). Checks, all with a temporary `HOME`: `python3 -m unittest discover -q` 257 OK (41 new in `test_model_fit.py`, which also pass on Python 3.9.6); `make_demo.py` and `build_release.py`; all six `node scripts/test_*.cjs` browser scripts pass (Playwright pointed at the existing browser cache with `PLAYWRIGHT_BROWSERS_PATH`). Demo `dashboard.html` grew from 1,879,335 to 1,886,583 bytes (+0.4 %). Real-data check (read-only, temporary output, one run): `fit --days 14` against the prototype's `ultra --days 14` run at the same time gave the same 84 sessions, 389 turns, 1,035 subagent runs, $373 model and $455 effort savings; total $2,371.35 against $2,370.78, the $0.57 being this live session's transcript that grew between the two reads. Full history: 8,550 units, `model_fit` 4.8 MB of JSON next to 127.5 MB of `request_stats`. Synthetic worst case: about 0.6 s of analysis per 100k requests.
- 2026-11-10: step 3 done (fifth tab "Model fit", built with text nodes only; renders while shown and again after live updates). Filters: period by unit/event `date`; project on units and events; role main = turns, subagent = agents and no main-thread events, auto-review = empty state; provider other than Claude = empty state; model = units whose cost-carrying `model` matches, switches by from/to, cold by model, effort changes and per-day counts hidden (not split by model); pool = the session's pool from `rows`, per-day counts hidden. A snapshot without `model_fit` shows an empty state. Example and session rows open the existing session dialog. The demo profile gained ten Claude Code sessions on current models (classes, over, under, effort above the guide, subagents with and without a model, a switch, a cold rewrite, effort changes); demo `dashboard.html` 1,886,453 to 2,050,112 bytes. Checks with a temporary `HOME`: `python3 -m unittest discover -q` 295 OK (294 at HEAD in a clean export, +1); `make_demo.py`; the six browser scripts (`test_dashboard.cjs` 24 scenarios, 7 new) and `capture_demo.cjs`; `build_release.py`.
- 2026-11-10: step 4 merged (rules, autopilot, sub-skills 2a40cce; docs and ADR 0005; hint and autopilot made independent opt-in switches); version 2.0.0. Step 5 moved to a follow-up.
- 2026-11-10: error-path review fixes, one commit, each with a test that fails before it: a model ID that is not text (Claude records, and Codex session_meta / turn_context) is an invalid record instead of crashing every command; a unit is `over` only when the guide's model is cheaper, and its savings never exceed its cost; units and events name models as `rows` do (dated IDs stay dated); `fit` applies `--project` / `--role` and refuses `--model`, `--pool` and a non-Claude `--provider`, `suggest` refuses all five; the launcher aliases only an untouched 1.x `aisad` command, follows only the sub-skill link on the `../..` route (a symlinked `skills/asi` is refused there too), never moves the data directory on reading commands (`version`, `rules`/`autopilot` `status|show`), refuses a read-only `CLAUDE.md`, reports an unreadable one, counts markers only alone on their line (a line of two markers is refused), removes the 1.x update lock with the 1.x skill, and exits 0 when only sub-skill links were skipped; the parse cache fingerprints a subagent's meta sidecar; `fit --session` shows runs whose main transcript is missing. Checks with a temporary `HOME`: unittest 310 OK, the three changed modules on Python 3.9.6, `make_demo.py` (demo gained a run on a dated Haiku ID), the six browser scripts (`test_dashboard.cjs` 25 scenarios), `build_release.py`, `release.py check --tag v2.0.0`. Noticed, not changed: `test_provider_limits` fails whenever `CLAUDE_CONFIG_DIR` is set (also at c9864cf).
- 2026-11-10: review fixes, one commit, tests fail before: the `fit --json` `days` breakdown keys each unit by its start date (it agrees with the dashboard tab and `--from`/`--to`); `fit_rates` applies the price rule's long-prompt multiplier above its threshold, so `suggest` re-read and switch costs are right for Haiku above 100k; the installer leaves no new `.aisad.update.lock` when it keeps a 1.x skill (a lock that existed stays); docs: the dashboard takes no period flags (ultraanalyze now says to use the Period filter), `under` explained the right way round, CHANGELOG note for menu bar app users. Checks with a temporary `HOME`.
