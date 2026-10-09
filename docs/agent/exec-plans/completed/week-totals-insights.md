# Week totals, spend intensity and deterministic insights

- Status: completed
- Source: 2026-10-08 user screenshot annotations.

## Goal
Add aligned weekly subtotals, five daily-spend colors and a script-generated budget/weekday summary to the terminal weekday matrix.

## Context and constraints
Python owns aggregates and analytics; Ink and portable Python render the same report. Preserve prices, global Claude/Codex budget scope, separate Grok basis and unknown observations. No transcript access, network, polling or guessed zero days. Preserve the unrelated local audit.

## Done when
Both renderers show correct totals and five intensity levels, deterministic summaries span month boundaries, and built/installed UI passes tests and PTY checks.

## Verification
Python accounting/analytics tests; Bun typecheck/layout tests; checked bundle/package; real PTY keys/resize; installed manifests.

## Out of scope
Tariffs, collector rewrites, actual invoices, new external analytics services.

## Current status
Implemented and installed locally for Claude and Codex. Both renderers show weekly Total rows, five daily-spend levels and Python-generated Insights. Following user authorization on 2026-10-08, real-data validation passed before commit/push and the update to PR #9. Real reports stay private; publication includes only code and non-private verification evidence.

## Next step
None; implementation and local verification are complete.

## Decisions and rationale
See [the Python/UI boundary ADR](../../adr/0001-optional-ink-terminal-ui.md) and [accounting rules](../../../ACCOUNTING.md). Forecasts use observed known-cost daily subtotals over 28 completed days, seven-day half-life weights and weekday-specific means when repeated data exists. They stop at calendar month end and retain explicit missing-price/day coverage.

## Verification evidence
2026-10-08, final local working tree:
- Python unittest discover: 117 passed, including 8 new analytics/totals tests.
- Strict TypeScript check and 13 Bun UI tests (67 assertions): passed.
- Bundle/build-release with source fingerprint checks: passed.
- Shared JSON tested for full-snapshot versus sliced UI history across the September/October boundary.
- Known $100/day scenario: depletion October 18, 10 days after October 8; current partial day and future records excluded from trend.
- Portable Python frame and actual React/Ink rendering fit Total and Insights into 80x24.
- Real PTY: matrix at 80x24, live resize to 110x40, Q and exact terminal restoration passed.
- Installed launcher: H/L/W/Q, Ctrl+C=130, offline network guard, Python fallback and headless modes passed.
- Both installed manifests/runtime/UI bytes match final source/build.
- Real local September/October history: independent Decimal aggregation reconciled daily, weekly and monthly known subtotals, missing/unpriced coverage, five bands, weekday means and the weighted budget forecast. One frozen snapshot avoids live-session drift.
- Installed Ink with real aggregate-only data: Total and Insights fit 80x24; September/October H/L, W, resize to 110x40, Q and terminal restoration passed with external networking blocked. Private data and terminal captures remain outside the repository.
- Raw diff and git diff --check passed. Preview of actual Ink-rendered synthetic aggregates saved privately; unrelated audit untouched.

## Feedback addressed
Closed months without priced observations must show unavailable/unpriced rather than $0. Weekly Total-row tests distinguish the row from the explanatory footer. Repeated all-zero days do not produce a misleading busiest-weekday claim.

## Open risks
Forecasts are conditional known-cost projections from available observations; absent logs and unpriced costs remain excluded. Cross-platform verification runs in PR #9 CI after publication.
