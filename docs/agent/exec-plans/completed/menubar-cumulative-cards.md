# Ship cumulative menu-bar cards

- Status: completed.
- Goal: make the selected C design the normal AISAD popup, using live aggregate data, then build and relaunch the app at its stable installed path.
- Relevant context: approved MenuCardsPreview cumulative layout, MenuBarView/UsageStore, MenuBarReport/CollectorClient and menubar_report; existing stable status-label image cache and snapshot-only launcher.
- Constraints: one collection supplies amounts and chart; preserve matched-window comparisons, price ranges/unknowns, calendar dates, day gaps and provider quota interactions. No new timer/network/settings/signing changes; keep status label/launcher identity unchanged. No commit or push.
- Done when: Today/Week cards and monthly cumulative chart render in production; current endpoint matches the month card; previous month is dashed; budget threshold and selected-day values work; tests/build/native captures pass; stable installed app runs the new code.
- Verification: baseline python3 -m unittest test_menubar -q and swift test --package-path macos; then Python full suite and native suite with meaningful new history-contract tests, Debug/Release builds, isolated native snapshots in both themes and edge states; live aggregate parity and launch/process/log evidence.
- Out of scope: full dashboard redesign, new providers, pricing catalog changes, unrelated SQLite redesign, publishing/commits/PR updates, Control Center/permission resets.
- First step: extend the aggregate menu report with bounded current/previous daily histories and decode/precompute cumulative points in AISADCore; replace spend rows with the approved cards while keeping native actions.


## Outcome

- Selected C is now the normal 300 pt popup: Today/Week cards, a larger month card with precomputed cumulative curves (solid current, dashed previous), saved-budget threshold, percent and reset countdown.
- One existing collection now includes bounded aggregate histories for current/previous calendar months. Dashboard updates and budget saves already use that same report, so chart and cards update together without another scan or schedule.
- AISADCore validates month lengths, adjacency, missing/future dates, pricing coverage and current chart/card totals. Cumulative points retain gaps, observed zeroes, unknown-cost flags and low/high price ranges. Aggregates contain no session IDs or source paths.
- Added pointer selection and keyboard Left/Right/Escape handling with chart accessibility labels. Seeded selected-day captures verify the rendered state; live native pointer/keyboard operation was not directly observed.
- Normal refresh/settings/dashboard/quit controls, provider hover cards, status-label image cache and snapshot-only launcher retain their existing owners and behavior.
- Baseline: 17 Python menu tests and 44 native tests passed. Final full suites: 176 Python tests and 50 native tests passed. Debug build (20.11 s) and Release build (65.23 s) passed.
- Reviewed actual production-view light/dark captures for 13 combinations: normal, selected, under/at limit, empty, zero, unpriced, partial, large, gaps, error, range and increased contrast. Range/subtotal information remains visible. Files: output/menubar-cumulative/{normal,selected,...}/menubar-{light,dark}.png.
- Updated ~/Applications/AISAD.app at its existing path with the verified Release executable and current collector resources. Bundle ID stays com.aiatsuk.aisad.menubar. The prior bundle is backed up at the path recorded in output/menubar-cumulative/install.json.
- Live collection validated in Python and the actual Swift decoder: the current-month total, price-coverage metadata and curve endpoint matched. Personal usage figures remain in ignored local verification artifacts.
- Relaunched the stable installed app. Runtime evidence records exactly one AISAD process, normal menu-bar startup and insertion=true. Its own report was generated after launch and includes monthly_history; the post-launch report also passed Swift calendar/endpoint validation.
- Evidence: output/menubar-cumulative/{python-tests.log,swift-tests.log,release-build.log,live-validation.log,runtime-validation.log,runtime.json,lifecycle.log,install.json}.
- Final raw diff and whitespace review passed. No commit/push, pricing/catalog changes, Control Center or permission changes, signing/certificate/key changes or network configuration changes.

## Publication follow-up

- The final chart disables the native focus effect while retaining pointer selection, keyboard Left/Right/Escape and accessibility labels. The Release app was rebuilt and relaunched after that correction.
- The user authorized committing all redesign work and pushing it to the existing PR. Source, synthetic checks and reproducible native-preview tooling are included; generated reports, app binaries, backups and personal figures remain in ignored local artifacts.
- Pre-publication gates: full Python and Swift suites, Release compilation, staged diff/whitespace review, explicit path staging, ordinary push and PR-head parity verification.
