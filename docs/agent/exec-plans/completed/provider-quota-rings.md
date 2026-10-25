# Provider quota rings and hover details

- Status: completed (implementation and native previews); ordinary launch remains blocked by the existing status-item visibility issue.
- Source: User reference and request, 2026-10-22
- Last updated: 2026-10-22 Europe/Moscow

## Goal

Replace the Limits tab and provider bars with one compact row of Claude/Codex/Grok rings in the spend menu. Hover shows a native popover containing all provider windows, remaining percentages, resets, plan and freshness.

## Relevant context

MenuBarView, ProviderLimitsView, ProviderLimitsStore, ProviderLimitsReport and native SnapshotExporter. Existing live quota adapters and cooldowns remain authoritative. Earlier work is uncommitted and preserved.

## Constraints

Preserve spend comparisons, monthly budget and daily whole-dollar menu label. No averaged/invented quota percentages. Missing/expired/stale readings remain explicit. No requests on hover. One Refresh updates both sources and respects cooldowns. No commits/pushes, new services, signing/credential/network or macOS visibility-setting changes. Preserve the separate blocked dashboard audit.

## Done when

The tab switch and provider bars are gone; rings and full detail popovers support keyboard/click access and cancellable hover dismissal. Data-state regressions, Swift build/tests and native light/dark/state previews pass. Full details remain available beyond the ring count.

## Verification

`swift test --package-path macos`; `./script/build_and_run.sh --build-only`; native offscreen menu/detail snapshots for live data and seven synthetic states; raw source/diff/whitespace review. Read icon visibility before one ordinary launch attempt.

## Out of scope

Dashboard changes, new quota adapters, pricing changes, macOS menu-bar visibility recovery, publication.

## Completed

- Removed Spend/Limits picker and separate Limits view; spend summary stays in the single menu.
- Added Claude/Codex/Grok provider row with independent remaining-quota rings.
- Added native hover popovers showing every quota window, plan, reset times, freshness, provider failures and retry cooldown.
- Added click/keyboard pinning and owned cancellable 200 ms hover-exit grace; switching/dismissal clears interaction state.
- Unified footer Refresh for dollar usage and provider quotas, preserving provider cooldowns.
- Added seven quota-summary regressions and five pointer/pinning state tests.
- Updated native snapshot exporter and repository documentation.

## Decisions and rationale

Ring fill means remaining quota. Follow-up hierarchy: the outer ring is short-term (normally 5 hours), the inner ring long-term (normally weekly), independent of source order. A weekly-only reading stays inside. Only aggregate limits occupy rings; model-specific windows never replace a missing aggregate. Details share the short-term-first order and prefer aggregate limits before model-specific peers of the same duration; all windows affect warning severity. Warning is below 20% remaining, critical at 10% or below. No averaging. Native popup owns layout/dismissal; the short hover grace lets the pointer cross its gap. Provider windows have no progress bars; the existing monthly dollar-budget bar is preserved.

## Verification evidence

- 35 Swift tests passed, zero failures; `output/quota-rings/swift-test.log`.
- Final native build/staging passed; `output/quota-rings/build.log`.
- Authenticated quota read in this turn returned available data for all three providers: Claude three windows, Codex/Grok one each. Actual timestamps retained in `output/quota-rings/live.json`.
- Native light/dark snapshots succeeded for live, available, cooldown, initial-cooldown, expired, unavailable (high contrast), loading and overflow states. Main menus and representative provider details visually inspected. Snapshots are offscreen view content, not a hardware hover session or native popup-chrome capture.
- Reviewed quota state, hover ownership, views, store, snapshot exporter and docs. `git diff --check` and explicit new-file whitespace validation passed.
- One `--verify` ordinary launch attempt failed its running-process check. Visibility read was 1 before launch and 0 afterward, reproducing the earlier macOS status-item issue. No visibility preference was changed in this task.

## Remaining limitations

Ordinary app launch remains blocked by the pre-existing macOS hidden/removed status item. Actual pointer traversal, Escape/outside-click behavior and VoiceOver have not been exercised in a running menu; pointer/pinning state transitions and native content layouts were tested. Do not treat offscreen screenshots as proof of hardware interaction. The unrelated dashboard visual audit remains separately blocked as recorded in its plan.

## Next step

Restore AISAD status-item visibility through the user's normal macOS controls, then manually confirm hover, pointer transfer, click pinning, Escape/outside dismissal and keyboard access. No further automatic preference recovery or launch retries.


## Follow-up: fixed period hierarchy and warning levels

- Replaced source-index ring sizing with explicit outer/inner placement shared across providers.
- Sorted ring selection, detail rows and accessibility descriptions by period, with aggregate limits before model-specific peers.
- Preserved remaining-quota fill and unknown/expired/stale handling.
- Added five regressions for reversed provider responses, weekly-only readings, legacy duration-free labels, other periods, and exact 20%/10% warning boundaries.
- Fresh baseline: seven quota tests passed. After the change: 12 quota tests and all 40 Swift tests passed; final native build/staging passed.
- Native light/dark previews of a deliberately reordered synthetic response verified 5h/weekly order, 19% orange, 10% red and weekly-only 20% inside; artifacts in output/quota-rings/hierarchy/.
- No ordinary launch retry, provider calls or preference changes in this follow-up. The existing runtime-hover verification limitation remains.


## Follow-up: Claude scoped weekly limits stay in details

- Ensured model-specific windows (normalized by the collector with a scoped title suffix) never occupy an aggregate ring, even when the aggregate weekly limit is missing.
- Kept all scoped windows in details and in warning severity. An exhausted Fable window raises the small red indicator while the session/aggregate-weekly ring fractions stay unchanged.
- Scoped-only healthy data shows an unknown aggregate indicator instead of suggesting an exhausted or invented aggregate ring.
- Added two regression tests covering missing aggregate windows, scoped-only data and exhausted Fable with healthy 84%/27% aggregate readings.
- Fresh baseline: 12 quota tests passed. After the change: 14 quota tests and all 42 Swift tests passed. Final native build/staging passed.
- Inspected native light/dark previews for healthy Fable (84%/27%/61%), exhausted Fable, missing aggregate weekly and scoped-only data in output/quota-rings/fable/. All synthetic snapshot commands exited successfully.
- No provider calls, login/visibility-setting changes or ordinary launch retries. Real hover remains unverified because of the existing status-item visibility problem.


## Runtime verification resolved

2026-10-22 14:05 MSK: icon visibility and real user hover/card behavior are now verified after clean reinstall, snapshot isolation and the approved Control Center association repair. The prior launch/pointer limitation is resolved. See [status-item-live-verification.md](status-item-live-verification.md) for fresh evidence and the exact fix.


## Follow-up: weekly percentage below provider names

- Added a compact second line such as "27% left" using the active aggregate weekly window. Session, Fable/scoped, monthly and expired windows are not substituted; unknown weekly allowance shows a dash.
- Reduced ring-to-label spacing from 6 to 3 pt and vertical button padding from 4 to 2 pt. Single inner rings now use their actual 14 pt layout width, removing the extra apparent gap for weekly-only providers.
- Healthy captions use secondary text; low remaining quota retains existing warning/critical colors.
- Added two semantic regressions for aggregate weekly selection across all providers, known zero, expired/missing/scoped/monthly readings and the weekly period tolerance.
- Fresh baseline: 14 quota tests passed. After the logic change: 16 quota tests and all 44 Swift tests passed. Final layout adjustment compiled and passed native preview verification.
- Inspected final native light/dark previews for available, expired, unavailable and cooldown states under output/quota-rings/weekly-caption/. Initial GUI fixture read from Documents stalled in Foundation file open; stopped only that snapshot PID and used system temporary fixture/output paths successfully. No privacy settings were changed.
- Updated ~/Applications/AISAD.app from the final build, preserving the previous installed bundle in ignored QA output; executable hashes matched.
- Fresh launch: normal PID 82980 is running the installed path, status visibility stayed 1, and live quota refresh completed for all three providers (2026-10-22 14:13 MSK).
- Final source/whitespace and git diff --check passed. No Control Center or other system setting changes were needed for this follow-up.


## Follow-up: calmer weekly captions and label spacing

- Increased ring-to-label spacing from 3 to 6 pt.
- Made every weekly caption use secondary text, including low and exhausted values. Existing warning indicators and detailed-card colors remain.
- Final native build passed. Inspected synthetic native light/dark snapshots in output/quota-rings/weekly-caption/calm/.
- Replaced the installed bundle with the final build; executable hashes matched. Fresh installed process PID 51429 is running and status-item visibility remains 1.
- Final source review and git diff --check passed. No data logic, system settings, signing configuration, commits or pushes changed.


## Follow-up: two-line weekly quota in the menu-bar label

- Goal: keep today's whole-dollar spend and append aligned Claude/Codex aggregate-weekly remaining percentages, based on the user's screenshot and example.
- Context: MenuBarStatusLabel, the existing ProviderLimitsStore and activeWeeklyWindow selection; preserve the working MenuBarExtra scene identity.
- Constraints/out of scope: monochrome; no extra provider requests, dashboard changes, commits/pushes, signing or system-preference changes.
- Implemented a single template image rendered from SwiftUI, preserving two rows in the status item. Reuses the existing active aggregate weekly window; scoped windows cannot substitute. Missing/expired data shows a dash; cached failure readings carry a tilde. Tooltip and accessibility include the weekly values.
- Validation: final build passed; all 16 existing quota-indicator tests passed; native light/dark captures inspected for normal 0%/75%, unavailable and cached readings. Captures under output/status-weekly-label/*-verified/.
- The first fixed 30 pt numeric column clipped ~100%. Measured its system-font width at 32.75 pt and increased the column to 36 pt; fresh captures show all glyphs. All three state captures have identical 290 x 56 pixel bounds (including preview padding).
- Snapshot and normal launch remain isolated. Updated the installed bundle; executable bytes match. PID 55724 is running ~/Applications/AISAD.app and status visibility is 1.
- Done: source review, build, native layout/state checks, installation and git diff --check. Desktop appearance itself is user-review evidence; offscreen captures establish native component rendering only.
- Apple references: https://developer.apple.com/documentation/swiftui/imagerenderer/nsimage and https://developer.apple.com/documentation/appkit/nsimage/istemplate


## Follow-up: quota-only status label with natural spacing

- User correction: remove the entire left spend/icon block; show only lowercase claude/codex lines without a numeric column.
- Removed the title input and its callers; replaced the grid/fixed percentage widths with two ordinary Text rows. Tooltip and accessibility now describe weekly remaining quota only.
- Kept the existing aggregate-weekly selection and unknown/cached semantics.
- Verification: final native build and git diff --check passed; inspected normal 0%/75% and cached ~0%/~100% native previews in both themes under output/status-weekly-label/*-quota-only/. No clipping in the inspected captures.
- Installed bundle executable matches the build. Finder did not start a normal process on this attempt; direct LaunchServices launch succeeded. Installed process PID 70230 is running and status visibility remains 1.
- Updated README. No system settings, signing configuration, provider collection rules, commits or pushes changed.


## Correction: native previews missed a normal-startup loop

The user's missing-icon screenshot disproved the earlier completion claim for the ImageRenderer status label. A real normal-process sample showed a launch-time image-update loop and 10.1 GB footprint, despite successful offscreen previews and a visible preference of 1. Replaced that rendering path with an app-owned AppKit template-image cache. Normal startup, provider refresh, a Control Center menu-bar displayable, menu appearance/dismissal and a later 29.2 MB footprint are now freshly verified. The user confirmed both lines are visible; see [status-label-startup-fix.md](status-label-startup-fix.md). No Control Center preferences were changed for this correction.
