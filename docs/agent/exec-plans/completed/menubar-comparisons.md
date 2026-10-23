# Menu bar period comparisons

- Status: completed
- Source: user follow-up, 2026-10-22
- Last updated: 2026-10-22 Europe/Moscow

## Goal
Show USD/percent changes against previous day, week and month under each menu bar total.

## Relevant context
Existing uncommitted feat/macos-menubar implementation, menubar_report, native SpendPeriod model
and native menu. Python owns calendar selection, prices and delta calculation.

## Constraints
Preserve existing working changes, displayed totals, monthly budget and refresh behavior.
No network, signing/configuration changes, commits or pushes. Keep missing data and uncertain prices explicit.

## Done when
Three comparisons render correctly, calendar/time/zero-baseline cases pass tests, the app is rebuilt
and relaunched, and native Light/Dark views are inspected.

## Verification
Baseline: python3 -m unittest test_menubar -q; swift test --package-path macos.
Final: python3 -m unittest discover -q; swift test --package-path macos;
./script/build_and_run.sh --snapshot <ignored output>; ./script/build_and_run.sh --verify;
git diff --check and raw review of changed functions/files.

## Out of scope
Changing CLI/statusline comparisons, limits, pricing, forecasts or release/distribution.

## Decisions
Compare the same local time of day, with Monday-based weeks. For shorter previous months,
compare the common complete days in both months and label the shorter comparison explicitly.
Retain exact window endpoints in aggregate JSON and expose them via the UI tooltip.
Suppress deltas for absent observations or uncertain pricing; a recorded zero baseline still
allows a USD delta and omits the undefined percentage.

## Current status
Implemented, inspected native Light/Dark captures and relaunched the local app.

## Next step
User review of the running menu; changes remain uncommitted on feat/macos-menubar.

## Verification evidence
2026-10-22:
- Baseline: 7 menu bar Python tests and 13 native tests passed.
- Final python3 -m unittest discover -q: 152 tests passed.
- Final swift test --package-path macos: 17 tests passed.
- New tests cover intraday cutoffs, Monday/week/year boundaries, short/leap months, DST,
  absent versus recorded-zero baselines, incomplete prices and signed native presentation.
- Native content captures inspected in Light/Dark under output/menubar-comparisons (ignored).
  The actual history produced available comparisons for all three periods.
- ./script/build_and_run.sh --verify: build passed and menu bar process running.
- git diff --check passed; updated Python/native code, tests and docs reviewed.
- Keyboard/VoiceOver interaction and minimum-OS runtime remain outside the local visual check.
