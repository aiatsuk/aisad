# Compact menu popup

- Status: complete
- Goal: make the main AISAD popup smaller and visually quieter, following the user's current screenshot.
- Context: MenuBarView, SpendPeriodView, MonthlyBudgetView and the provider summary row; existing native snapshot exporter and synthetic fixtures.
- Constraints: preserve values, comparison semantics, all actions and hover/cards. Keep the working two-line status label and image cache untouched. No provider/collector/settings/signing changes, commits or pushes.
- Done when: the popup is narrower and shorter than its fresh baseline, amounts and actions remain readable in both themes, extreme/empty/error content is not clipped, and the installed app reaches normal startup.
- Verification: native before/after captures with identical fixtures; build-only command; representative stress-state previews; final source/whitespace review; fresh installed startup events and process path.
- Out of scope: dashboard, quota adapters, business calculations and provider-detail redesign.

## Outcome and verification (2026-10-22)

- Main popup: 280 x 243 pt with the normal fixture, versus 320 x 276 pt before (about 23% less area). Reduced spacing, quieter secondary type and footer actions, thinner monthly budget gauge. Preserved ring-to-label spacing and quota-card behavior.
- Native light/dark captures reviewed in output/compact-menu-polish/before and after. Extreme cost ranges, loading, refresh error and opening-dashboard captures also reviewed; amounts and status text remain visible.
- Build succeeded with ./script/build_and_run.sh --build-only; log: output/compact-menu-polish/build.log. Reviewed final source; git diff --check and whitespace checks for the four untracked view files passed. No collector, calculation or status-label changes.
- Installed matching binary into /Users/aiatsuk/Applications/AISAD.app; previous bundle retained under output/compact-menu-polish/previous-installed-bundle-20261022T135352Z. Installation details: output/compact-menu-polish/installation.json.
- Fresh runtime: PID 83243 from the installed path; normal lifecycle event at 16:53:53 MSK, quota refresh for all three providers at 16:53:54. Control Center accepted the client and created a .menuBar displayable at 16:53:53. Process was idle at 0% CPU, RSS 74224 KB at the verification checkpoint.
- Native previews use synthetic fixture values; live pointer interaction was not repeated for these presentational changes. No commits or pushes.
