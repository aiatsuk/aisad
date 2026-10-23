# Dashboard: data and logic audit

Date: 2026-10-22. Scope: fresh local collection, standalone report logic, filter/date arithmetic and copy. This is **not a completed visual audit**: the in-app browser rejected file:// and explicitly prohibited alternate-surface workarounds. No browser fallback, screenshot reuse, server or listener was used.

## Findings and corrections

1. **Important — unknown Grok cost displayed as zero** (`agent_usage.py:2541`). A period whose Grok records all lacked reported cost rendered “$0.00 known reported.” Added an explicit “Cost unavailable” state while preserving genuine reported zero and incomplete known subtotals. Regression reproduced the old output before the fix.
2. **Clarity — session counts described different populations** (`agent_usage.py:2531`). Charts count sessions with usage observations; Sessions also contains event-only sessions. Both captions now state their population.
3. **Clarity — empty tables looked unfinished**. Models, sessions, cache and event-preview tables now explain empty dates/searches instead of leaving just a header.
4. **Clarity — freshness and themes**. Snapshot time includes its display timezone; the footer explains how to recollect from AISAD or the CLI. Initial theme follows the system, with a remembered explicit choice when storage is available. Restricted storage remains recoverable.
5. **Accessibility semantics**. Tables have descriptive accessible names; session result counts announce changes politely. Actual assistive-technology behavior remains unverified.

## Flow coverage in this run

| Step | Surface/task | Result | Evidence and limits |
| --- | --- | --- | --- |
| 1 | Collect and open data | Data verified | HTML, usage JSON and status timestamps, rows and summaries matched. Browser open was blocked. |
| 2 | Charts, dates and filters | Logic verified | Day/week/month and all-history totals, tokens and cost parts reconciled. Calendar and filter functions passed without a browser. |
| 3 | Sessions, search and detail | Logic verified; copy fixed | Synthetic report execution checked search misses, event-only sessions, detail opening and the difference between the two counts. Actual pointer/focus behavior was not tested. |
| 4 | Context | Calculation paths checked | Shared aggregation and telemetry rendering ran in synthetic non-browser tests. No current screenshot or layout evidence. |
| 5 | Cache usage | Data verified; empty state fixed | Cached + uncached + written input identities and cost components reconciled; filtered rendering logic passed. |
| 6 | Grok reported totals | Defect fixed | Unknown, actual zero and partial-known cases passed a regression using the shipped report logic. |
| 7 | Themes and narrow layout | Theme decision logic verified; visual check blocked | System preference, explicit preference and denied-storage cases passed. Responsive layout and actual theme appearance are not newly verified. |

## Fresh evidence

- Latest verified collection: **2026-10-22 15:38:42 Europe/Moscow**.
- **38,787 observations, 792 sessions, 831 files**.
- HTML/public snapshot matched the persisted usage and status data.
- Zero token-part, cost-part, total, grouped-versus-request or request-statistics invariant failures.
- Grouping reconciliation: 2 providers, 13 models, 46 projects, 3 roles, 1 observed pool.
- Day, Monday-based week and calendar month totals matched across raw normalized requests, grouped rows and per-request statistics.
- Current saved price catalog: 2026-10-22, models.dev rates.
- Python: **172 tests passed**. One existing synthetic HTTP-429 cleanup ResourceWarning appeared; it was not a test failure or a live network request.
- Non-browser Node suites passed: dashboard states, calendar periods, pricing view and offline loader.
- Local development bundle rebuilt with the current collector. No commit, push or publication.
- Aggregate-only audit and local checker: `output/dashboard-audit/` (ignored).

## How freshness works

Dashboard recollects local history when opened from the menu, writes a standalone HTML file and returns the same calendar-spend report to the menu. Both surfaces then use the same collection timestamp, totals, comparisons and saved monthly limit. The saved page does not collect or poll. Refresh it by opening Dashboard again in AISAD, or running `aisad dashboard`; an already open browser tab may also need reloading. Files are read up to their starting size, so updates made during a collection can appear on the next collection.

## Limits

The data is current for the discovered local traces as of the timestamp, not a complete cloud history or an invoice. This snapshot has 4,156 registered Codex chats without local trace files; those chats are not estimated. Existing processing-tier/model-alias assumptions remain unchanged. Grok reported costs remain separate from the Claude/Codex API-equivalent estimate.

A fresh visual walkthrough, mobile reflow, zoom, contrast and actual keyboard/screen-reader interaction still need permitted browser access or user-provided screenshots. The audit skill's evidence rule is: “Do not claim an audit if the actual flow could not be accessed and captured.” Source: [product-design:audit](/Users/aiatsuk/.codex/plugins/cache/openai-curated-remote/product-design/0.1.56/skills/audit/SKILL.md).


## Follow-up: shared calendar report and presentation

- Dashboard and menu now share one aggregate report from the same collection. Native Dashboard updates the menu report before opening the file, without a second scan or reading a potentially older report file.
- Added a restrained global summary for today/week/month with saved monthly budget progress. Detail filters remain below it and their scope is explicit. Amounts/deltas stay neutral; only budget progress uses warning colors.
- Added Today and This month detail presets. Calendar day/week/month comparisons use the same local-clock cutoff as the menu, including DST and shorter previous months. Provider table deltas use the same matched current window.
- Known partial costs carry a plus sign; incomplete prices suppress monetary deltas. Tiny cost ranges use the same completeness tolerance as Python.
- Fresh snapshot: 2026-10-22T12:38:42.715724Z. Today $405.84, week $1,545.64, month $2,916.28. Budget $2,000.
- Repriced all 38,787 normalized observations against the exact saved catalog; no cost/component/range mismatches. Raw, grouped, per-request, HTML and shared native report all agree.
- Executed the shipped JS with the fresh snapshot in Node DOM stubs: displayed daily/weekly/monthly amounts and both comparison windows match the canonical menu report. This is logic evidence, not browser or visual evidence.
- Python 172 tests passed; Swift 44 tests passed; dashboard-state, calendar, pricing and loader Node suites passed. Final native build and source/bundled-collector hash check passed.
- Installed the final bundle in ~/Applications/AISAD.app with an ignored backup. PID 4724 is running that path; visibility remains 1 and all three provider refreshes completed.
- Full visual/browser walkthrough remains blocked. No alternate browser, listener or policy workaround was attempted. Current screenshot feedback is still needed before claiming the layout is visually reviewed.
