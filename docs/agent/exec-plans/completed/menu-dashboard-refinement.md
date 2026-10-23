# Compact menu controls and dashboard freshness

- Status: completed
- Source: User screenshots and dashboard check, 2026-10-22
- Last updated: 2026-10-22 12:48 MSK

## Goal

Move Spend/Limits into the header as a compact native icon switch, tighten the footer, remove duplicate stale-provider captions, and ensure Dashboard opens a freshly collected snapshot.

## Relevant context

MenuBarView.swift, ProviderLimitsView.swift, CollectorClient.swift, existing dashboard renderer and browser regressions. Shared output dashboard is dated 2026-10-19; the current native action reuses it indefinitely.

## Constraints

Preserve ongoing uncommitted changes, cost semantics, quota cooldowns, and accessible stale/error information. No commits, pushes, credentials/signing/network configuration changes, or dashboard server.

## Done when

Native light/dark snapshots are reviewed; existing windows no longer show duplicate captions; dashboard recollects on every open, fails explicitly without destroying the previous HTML, and displayed totals match its collected rows. The snapshot timestamp is visible in the browser header and models.dev rates are identified correctly.

## Verification

swift test --package-path macos; native fixture snapshots; existing offline-loader and dashboard/calendar/pricing/evidence browser regressions; live shared-output collection and browser reconciliation; ./script/build_and_run.sh --verify; git diff --check and focused raw diff review.

## Out of scope

Dashboard redesign, live browser polling, new providers, subscription billing reconstruction, publication.

## Current status

Completed. Updated local bundle is running, native layouts and dashboard behavior are verified.

## Completed

- Moved the native segmented picker into the header with dollar/gauge SF Symbols.
- Tightened root/footer spacing and reviewed real native views in both appearances.
- Removed provider cooldown/last-known caption rows when windows exist; retained status/age in tooltips and accessibility, with a small stale-status icon.
- Changed Dashboard to recollect every time, with a bounded five-minute collection timeout and explicit failure handling.
- Added an integration regression: a newly created synthetic trace appears on the second open; failed collection does not open or overwrite the last successful HTML.
- Moved browser snapshot time into the header and fixed models.dev rates being labelled Custom rates.
- Added browser and static-fallback regressions for price-source labels.

## Next step

None. Ready for user review; no commit or push.

## Decisions and rationale

Use the native segmented picker with SF Symbols. Keep stale source/age in tooltips and accessibility; keep visible guidance when no windows exist. Dashboard remains an explicitly dated offline snapshot.

## Failed approaches

None.

## Verification evidence

- Python: 171 tests passed, including offline HTML fallback and existing pricing/usage coverage.
- Swift: 23 tests passed, including repeat-open freshness, error preservation and shared budget isolation.
- Browser: 17 dashboard scenarios passed; calendar, pricing, loader and session-evidence suites also passed.
- Actual shared-output HTML, usage.json and status.json timestamps and summaries matched.
- Latest verified dashboard snapshot: 2026-10-22 12:45:16 Europe/Moscow; 37,299 observations, zero unpriced rows.
- Chromium matched all six totals: day, calendar week, calendar month, Claude month, Codex month and all history. Sessions and weighted cache ratios matched too. No page errors or external requests.
- Native day/week/month aggregation reconciled with the same snapshot's dashboard rows, all three passed.
- Full real collection took 61.89 seconds initially and 26.37 seconds with the warm cache.
- Native screenshot review: live Spend/Limits light/dark, cooldown state, unavailable increased-contrast state, dashboard Opening and empty loading state. All 12 SF Symbols were available.
- Screenshots and aggregate browser audit: output/menu-dashboard-refinement/ (ignored, machine-local).
- git diff --check, explicit whitespace checks for changed Swift/test files, shell syntax and focused raw diff review passed.
- ./script/build_and_run.sh --verify passed with the final bundled collector; local AISAD menu process is running.

## Open risks

The browser remains an offline snapshot between Dashboard opens; existing tabs may require reloading after a new collection. Large histories may take tens of seconds to collect. Dollar figures remain API-equivalent estimates with the existing pricing/history limitations. Native keyboard and VoiceOver interaction was not automated; standard control rendering, labels, busy states and symbol availability were checked.
