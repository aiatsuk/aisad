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
- [ ] 2. Model fit engine and `fit` / `suggest` commands in `agent_usage.py`, with tests (section "Model fit engine").
- [ ] 3. "Model fit" tab in the HTML dashboard, with browser tests (section "Dashboard").
- [ ] 4. Rules block and autopilot in the launcher, four sub-skills, installer links, docs (ADR 0005, README, SKILL.md, CHANGELOG 2.0.0, VERSION 2.0.0).
- [ ] 5. Terminal (Ink) view. Second step: only after 1 to 4 pass; otherwise it becomes a follow-up and the PR says so.
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
