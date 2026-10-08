# Optional TypeScript/Ink terminal UI

- Status: completed
- Source: User approved a separate TypeScript/React/Ink UI with Bun builds.
- Last updated: 2026-10-08 Europe/Moscow

## Goal
Provide a component-based, resize-aware AISAD terminal dashboard while preserving Python collection, costs and offline operation.

## Relevant context
agent_usage.py chart reports and weekday_view; existing W/H/L/Q navigation; scripts/build_release.py; installed Claude/Codex skills.

## Constraints
Strict TypeScript. Public upstream Ink/React only. Transfer aggregate reports, never transcripts. No polling/network in the dashboard. Keep Python-only snapshot and fallback UI portable. Preserve uncommitted chart work and the unrelated usage-history-audit plan. The implementation request excluded publication. The subsequent 2026-10-08 user request explicitly authorizes testing, commit, push and updating the existing PR; release publication remains outside scope.

## Done when
Bun bundles the UI and its dependencies; the checked local skill ZIP installs it; aisad chooses it in a terminal when Bun exists, and falls back to Python otherwise. Daily graph and Sunday-first week matrix retain correct costs, labels and month navigation. Resize and exit restore the terminal.

## Verification
bun run check; bun test; Python unittest discover; release checks/build; temporary PTY keyboard/resize/exit tests; installed manifest and CLI checks.

## Out of scope
Collector rewrite, pricing changes, Commander migration, native addons, ripgrep integration, proprietary Claude code, background services and GitHub publication.

## Current status
Implemented, built and installed locally for Claude and Codex. Subsequent delivery is tracked in PR #9; the user explicitly authorized commit, push and PR publication on 2026-10-08. Final source diff reviewed.

## Completed
- Strict TypeScript, React 19.3.0 and public upstream Ink 8.0.0, built by Bun 1.2.22.
- Python passes only monthly aggregates. Existing pricing, budgets, snapshots and JSON remain authoritative.
- Daily graph and Sunday-first matrix retain known values, gaps and coverage; matrix cells show only costs, without day numbers; W/H/L/arrows navigate loaded data. Resize redraws without another keypress.
- Checked ZIP includes the roughly 404 KiB bundled UI and dependency notices. Both installed manifests match every file hash. Saved real budget remains $2,000.
- Python fallback works without preparing UI data when Bun is missing or AISAD_TERMINAL_UI=python.

## Next step
None; implementation and local installation are complete.

## Decisions and rationale
See [ADR 0001](../../adr/0001-optional-ink-terminal-ui.md). Bundle one optional module rather than introducing platform binaries or rewriting the collector. Keep Python-only operation available.

## Failed approaches
Bun resolves Ink's optional development-only DevTools import before dead-code elimination. A process.env define alone did not remove it because Ink imports node:process; a build-only plugin now disables the pinned public dependency's gate and fails if its marker changes. Dependency source files remain untouched.

Initial PTY checks stopped consuming output during exit and blocked writes; continuing to drain the PTY verified normal exit. A network test also incorrectly rejected Yoga's local data URI; the corrected guard allows data URIs while rejecting external fetches and socket operations.

## Verification evidence
2026-10-08, local uncommitted working tree:
- python3 -m unittest discover -v: 109 passed.
- bun run --cwd ui check: strict typecheck passed.
- bun run --cwd ui test: 10 tests, 58 assertions passed.
- bun run build: byte-identical bundle, notices and metadata on repeated build.
- python3 scripts/release.py check --tag v1.2.0 and scripts/build_release.py --with-ui: passed; stale source metadata rejected by a synthetic test.
- Local ZIP installation to both skill directories and existing aisad launcher: passed; both complete manifests verified.
- Bun UI PTY: W toggle, live SIGWINCH resize, Q, selected state and terminal restoration passed.
- /tmp/aisad-installed-ink-check.py: installed launcher selected Bun; H/L/W/Q and Ctrl+C=130 restored the terminal. External fetch/socket operations were blocked. Python fallback passed; JSON/snapshot never launched Bun.
- git diff --check: passed. Unrelated usage-history-audit plan preserved.
- Subsequent publication check on 2026-10-08: all 109 Python and 10 UI tests/typecheck/build passed; installed PTY navigation/offline/fallback checks passed; calendar/pricing/offline-loader, 14 browser dashboard scenarios, session evidence and responsive/offline capture checks passed using synthetic data. Screenshot output was redirected to a temporary file, preserving docs/dashboard.png.

## Open risks
Verified actual terminal behavior on this macOS device. Cross-platform CI checks are configured but have not run for these uncommitted changes. The portable fallback remains available.
