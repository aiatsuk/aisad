# Dashboard data audit and polish

- Status: blocked (visual walkthrough only)
- Source: User request, 2026-10-22
- Last updated: 2026-10-22 15:40 MSK

## Goal

Verify current dashboard data, period/filter calculations and session details; fix confirmed defects and improve clarity and empty states.

## Relevant context

agent_usage.py is the collector and standalone HTML renderer. Shared output is ~/.local/share/aisad/output. Prior native-menu work is uncommitted and must be preserved. Product Design audit skill selected for a fresh flow audit.

## Constraints

No commits, pushes, publishing, server/listener, credential/signing/network changes or personal transcript output. No agents. Browser policy denied file:// and explicitly forbids workarounds: no alternate browser or indirect route to the blocked file. Source/data checks and non-browser Node unit tests remain available.

## Done when

Latest HTML/usage/status agree; normalized rows, requests and totals reconcile; confirmed rendering defects have regressions; refreshed bundle includes changes. Full visual walkthrough requires valid new screenshots or an allowed existing web target.

## Verification

python3 -m unittest discover -q; node scripts/test_calendar_periods.cjs; node scripts/test_pricing_view.cjs; node scripts/test_offline_loader.cjs; new non-browser rendering-state regressions; aggregate-only live reconciliation; git diff --check; ./script/build_and_run.sh --build-only.

## Out of scope

New hosting, live browser collection, pricing policy changes, external sharing, redesign without visual verification.

## Current status

Data/logic work and local packaging are finished. Current snapshot passed on 38,787 observations, with exact saved-catalog repricing and shared menu-report parity. Full visual walkthrough remains blocked by the browser URL policy; no visual-completion claim.

## Completed

- Read existing collection/normalization, filtering, aggregation, chart, session and cache code.
- Confirmed grouped totals, input/output identity and cost components reconcile.
- Observed a newer shared snapshot since the previous turn, consistent with the current native refresh-on-open behavior.
- Fixed Grok missing-cost-as-zero, preserving known zero and partial subtotals.
- Clarified event-only versus usage session counts; added explanatory empty table states.
- Added table accessible names, result-count announcements, timezone and recollection copy.
- Added system theme defaults and remembered explicit choices with safe storage failure handling.
- Added dependency-free Node state regression to CI and documented the non-browser verification path.
- Rebuilt the local bundle with the final collector.
- Detailed results: docs/agent/reports/dashboard-data-audit.md.

## Next step

Obtain user-provided screenshots or an existing permitted web target for the remaining visual walkthrough.

## Decisions and rationale

Treat missing cost as unknown, preserve actual known zero and label incomplete subtotals. Keep snapshot semantics explicit. Do not claim current visual audit or screenshot evidence without an allowed capture.

## Failed approaches

In-app browser rejected local file://; only HTTP/HTTPS are permitted and policy forbids alternate-surface workarounds. No retry or bypass attempted.

## Verification evidence

- Latest collection: 2026-10-22 13:00:22 Europe/Moscow, 37,494 observations, 782 sessions, 821 files.
- HTML/usage/status agreement; request/grouped/statistics and day/week/month reconciliation passed with zero invariant failures.
- Group checks passed for 2 providers, 13 models, 46 projects, 3 roles and 1 observed pool.
- Python: 171 passed; non-browser dashboard states, calendar, pricing and loader Node suites passed.
- Synthetic HTTP-429 cleanup ResourceWarning appeared in the existing Python fixture suite; no test failed.
- ./script/build_and_run.sh --build-only passed.
- No actual browser regression or current screenshot was obtained; blocked file:// action was not retried or bypassed.
- Raw renderer/test/CI changes reviewed; git diff --check and explicit new-test whitespace check passed. Bundled collector SHA-256 equals the current source. Data/logic work is ready for review; visual work remains blocked.

## Open risks

Visual layout, actual keyboard navigation and browser rendering cannot be rechecked in this run until a permitted target or user-provided screenshots are available.


## Follow-up contract: dashboard and menu consistency

- Goal: refresh and reconcile day/week/month spend, calendar comparisons and saved budget between the dashboard and menu, then simplify their presentation.
- Context: current collector, shared output, native CollectorClient/UsageStore and existing rendering regressions.
- Constraints: preserve prior work; no commits/pushes, hosting, listener, credentials, signing or network settings; browser file policy remains binding. No agents.
- Done when: one dashboard collection supplies both UI reports, calendar totals and matched-clock comparisons agree, new/unknown/zero/partial data states have meaningful regressions, installed app contains the result.
- Verification: Python unittest discover; non-browser Node dashboard/calendar/pricing/loader suites; Swift tests and native build; aggregate-only live reconciliation; final raw diff/whitespace review.
- Out of scope: live cloud history, subscription billing, pricing policy changes and browser-policy workarounds. Visual polish is limited to existing layout/clarity until a permitted current screenshot is available.
- Fresh baseline: 26 relevant Python tests and dashboard-state suite passed. Local snapshot 2026-10-22T12:31:12Z: 38,690 observations, 789 sessions, 828 files; raw/grouped/request-stat totals match.
- Confirmed gaps: rolling-week default differs from calendar week; native report is not updated after dashboard collection; prior-day comparison includes hours beyond the menu cutoff; partial-priced comparisons can display an unjustified percentage.


## Follow-up result

Data, calculation, layout-source and installation changes are ready; current browser appearance is unverified. Shared collection parity, Python/JS matched-calendar deltas, per-provider comparisons, partial-pricing handling and budget scope are covered. Final Python/Swift counts: 172 / 44; all four non-browser Node suites passed. Live report generated 2026-10-22T12:38:42.715724Z; Node execution with that actual snapshot displayed the same $405.84 / $1,545.64 / $2,916.28 totals and comparison aggregates as the menu report. Installed process PID 4724, status visibility 1, three live quota refreshes completed. No commit, push, signing/settings change or browser workaround.

Remaining step: inspect a current user-provided screenshot or a permitted existing web surface, then evaluate spacing, reflow, contrast and actual keyboard flow. The audit skill prevents a full visual-completion claim without captured evidence.
