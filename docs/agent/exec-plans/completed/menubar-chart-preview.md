# Menu-bar chart prototype

- Status: completed
- Source: user request to inspect the CLI chart, test a compact menu-bar adaptation and show how it would look.
- Goal: reviewable native light/dark previews of a compact calendar-month daily-spend chart inside the existing 280-point popup.
- Relevant context: terminal_chart_report, ui/src/minimap.ts, MenuBarView and the isolated SnapshotExporter. Mobbin Shopify and Base44 analytics references inform chart density.
- Constraints: reuse the CLI aggregate semantics; preserve gaps, future days and incomplete-price status. Scope chart to Claude/Codex API estimates to match the menu's monthly amount. Synthetic display fixtures only. Keep normal app/collector/status label unchanged; no installation, commit, push, signing/settings changes or extra quota requests.
- Done when: actual colored CLI snapshot has been inspected; two native densities and a selected-day state are rendered and visually checked; empty, missing, zero and partial-price states stay honest and legible; builds and relevant data/interaction checks pass.
- Verification: actual offline CLI snapshot; Swift build and native offscreen captures in light/dark and high contrast; aggregate parity with terminal_chart_report; native core tests; final raw diff and whitespace review.
- Out of scope: production data wiring, new collection schedules, month navigation, Grok price mixing, full dashboard changes and deployment.
- Current status: clean baseline on 0c497bb; Mobbin references examined. Existing CLI chart is daily cost per provider across the full calendar month, not cumulative spend.
- Next step: choose a density before production wiring; chart data can be added to the existing collection without a second scan.


## Outcome

- Inspected the actual offline colored CLI chart. It is daily known cost across a full calendar month, with provider series, a shared vertical scale and blank missing/future days. CLI Grok costs are separately provider-reported.
- Added a DEBUG-only adapter for existing CLI aggregate JSON and a native Swift Charts prototype. Normal MenuBarView receives no chart data; installed AISAD, normal registration, collection and status-label cache remain unchanged.
- Two layouts: regular 280 x 367 pt and compact 280 x 320 pt. The same fixture baseline is 280 x 243 pt. The compact view keeps legend and month on one line and adds 77 pt.
- Native light/dark captures: output/menubar-chart-prototype/{regular,compact,selected}/. A selected-day capture shows exact provider amounts in the legend without another popover.
- Eight synthetic scenarios from terminal_chart_report retain exact menu monthly totals: normal, empty, zero, fully unpriced, gaps, partial pricing, large costs and isolated observations. The isolated Swift adapter harness passed all eight; zero, future/missing days, partial plus signs, segment breaks and singleton points were checked.
- Reviewed native normal/selected, empty/unpriced, zero, gaps, partial, large and isolated-day states, plus high-contrast capture. The final monthly axis includes the last day; gaps remain unjoined and isolated known days retain visible points.
- Existing native suite: 44 passed. Debug bundle and Release build passed; the prototype is excluded from Release. Final tracked diff and new-source whitespace checks passed.
- Native live pointer/keyboard interaction is unverified; selected-day screenshots seed state directly. No screenshot is claimed as an installed live UI.
- The initial compile needed an explicit compactMap result type. Initial partial/large fixtures selected a previous-month row; they were corrected to current-month data and their assertions and captures rerun.
- No installation, commits, pushes, settings or signing changes.

## References

- Shopify: https://mobbin.com/screens/d7a58dca-0c9c-4e1b-b731-469e02c8a34b
- Base44: https://mobbin.com/screens/52f03ce9-acb4-4bc8-8a53-03b7e8054c96

The references informed chart density and restrained axes; the prototype uses native macOS controls and the existing AISAD layout.

## Follow-up: current versus previous month

- Status: completed.
- Goal: replace provider-colored series with aggregate Claude/Codex daily costs: current month solid, previous month dashed, aligned by day number.
- Relevant context: existing DEBUG snapshot prototype and terminal_chart_report numeric aggregates.
- Constraints: current month stops at as-of date; previous month uses available complete days; today's spend remains partial. No fabricated zeroes or nonexistent dates. Keep pricing coverage, stable status item and installed app unchanged.
- Done when: current/previous totals and aligned dates are checked, native light/dark and selected-day previews are legible, gaps and shorter months remain honest.
- Verification: Debug bundle build; actual Swift adapter harness; native offscreen snapshots; raw diff and whitespace review.
- Out of scope: production wiring, app installation, CLI behavior changes, commit/push.


### Comparison outcome

- Replaced provider series with combined Claude/Codex daily totals. Current month uses a solid blue line; previous month a gray dashed line. Both share one USD scale and align by day number.
- Current month ends at the as-of day (today remains partial). Previous month shows its available full daily values. The selected-day legend displays both exact costs; absent dates show No data and incomplete known subtotals retain a plus sign.
- Compact layout remains 280 x 320 pt for the normal fixture. Native light/dark captures are in output/menubar-chart-comparison/{compact,selected}/. They are synthetic previews, not captures of the installed app or proof of live pointer interaction.
- Actual Swift adapter checks passed 10 pairs generated by terminal_chart_report: normal, empty, current-empty, zero, unpriced, gaps, partial, large, isolated and February versus January. Aggregated current totals match menubar_report; invalid calendar dates and unrelated comparison months are rejected.
- Native normal/selected, empty/zero/unpriced, gap, partial, large, isolated, shorter-month and high-contrast states were rendered and visually reviewed.
- DEBUG bundle build passed (13.84 seconds after fixing generated source newlines). Final raw diff and whitespace review passed. Existing normal status item, installed app, collection, CLI and prices are unchanged.
- No installation, commits, pushes, network/settings or signing changes. Live pointer interaction remains unverified; the selected-day screenshot seeds state directly.
