# Menu bar visual review and iterations

- Status: completed
- Source: user requested icon/design checks and several improvement iterations, 2026-10-22
- Last updated: 2026-10-22 Europe/Moscow

## Goal
Improve the compact native AISAD menu's icons, hierarchy, actions and exceptional states through three captured iterations.

## Relevant context
Existing uncommitted feat/macos-menubar. MenuBarView, the menu bar label and BudgetSettingsView.
Use SF Symbols and native controls; Python pricing, periods and saved limits remain authoritative.

## Constraints
Preserve user work, current calculations, limits and refresh ownership. No new dependencies,
network/signing changes, personal-budget edits, commits, pushes or app installation.
Preview fixtures are DEBUG-only and never replace live startup data.

## Done when
Three iterations have fresh native captures, final normal/edge states are inspected in Light/Dark,
symbols resolve on the installed OS, native checks/build pass and the live app is relaunched.

## Verification
swift test --package-path macos; ./script/build_and_run.sh --snapshot <ignored output>;
DEBUG fixture captures, symbol-resolution checks, git diff --check and targeted raw diffs;
./script/build_and_run.sh --verify.

## Out of scope
Provider quotas, new business features, branding/app icon generation, release signing and full desktop accessibility certification.

## Audit scope and evidence limits
Visual review of native content trees, status label and settings; not a desktop capture or a completed
keyboard/VoiceOver/pointer interaction audit. Captures are from this run under output/design-review.
System Light/Dark and local high-contrast NSAppearance previews can be inspected without changing OS settings. Reduce Motion remains a manual verification gap.

## Baseline — 00-baseline
Captured/inspected native Light/Dark. All primary totals and monthly progress fit.
Risks: footer icons have different visual sizes and no visible labels; small gray text weakens hierarchy.
Version and timezone are already available through the title tooltip.

## Iteration 1 — icons and actions
01-icons: inspected menu, settings, symbol board and status label. Eight SF Symbols resolve on the installed OS.
Refresh and Budget are visibly labelled; gearshape consistently represents settings.
Status symbol and percentage use explicit monochrome rendering. No extra period decoration added.
Finding for next pass: month cost is shifted left by the inline limit; labels need clearer hierarchy.

## Iteration 2 — text hierarchy and alignment
02-hierarchy: inspected Light/Dark menu and settings. All totals now share the right edge;
the monthly limit sits beside progress, while comparisons use a lighter regular weight.
Provider and estimate metadata is separated; settings copy explains scope without CLI implementation detail.
Native menu remains 320 points wide and about 261 points tall on normal data.

## Iteration 3 — state/contrast review
03-states: inspected under-limit, warning, zero, no-data, unpriced, partial-price, very large range,
error, loading, stale and local high-contrast-appearance previews. Symbols resolve and numbers remain visible.
03-refined: corrected and rechecked duplicate loading spinners and repeated pricing notices.
The 65–100% warning bar now uses orange; exceeded limits stay red.
Inspected loading, partial/unpriced totals, very large ranges and saving/saved settings captures.
All nine interface symbols, including the saved checkmark, resolve and render.
No observed clipping in the inspected states.
The preview run verified that the real shared budget file content was unchanged.

## Current status
All three iterations completed; final native Light/Dark menu inspected on live data and app relaunched.

## Next step
Review the running AISAD menu; publication remains out of scope.

## Verification evidence
2026-10-22, base 7076765, uncommitted feat/macos-menubar:
- swift test --package-path macos: 17 tests passed on the final source.
- ./script/build_and_run.sh --snapshot output/design-review/04-final-live:
  actual live menu, settings, status label and symbol board rendered in Light/Dark.
- Final live menu content is 320 x 261 points (640 x 522 capture pixels).
- All nine SF Symbols resolved through NSImage on the installed macOS.
- Native settings captures include normal, saving and saved states; preview fixtures are DEBUG-only.
- Fixture previews verified the real budget file hash remained unchanged.
- ./script/build_and_run.sh --verify: fresh build passed; live menu bar process running.
- git diff --check passed; targeted before/after source diffs reviewed.

## Remaining evidence limits
Native NSHostingView captures show the real component tree, not the actual desktop menu presentation.
Mouse, keyboard focus, VoiceOver, minimum macOS 14 execution and OS accessibility-setting behavior
were not manually exercised. Local high-contrast NSAppearance captures do not establish full
system Increase Contrast or Reduce Motion compliance. No OS settings were changed.

## References
- Apple SF Symbols: https://developer.apple.com/design/human-interface-guidelines/sf-symbols/
- Apple symbol rendering: https://developer.apple.com/documentation/swiftui/symbolrenderingmode
