# Status label startup loop

- Status: completed
- Source: user screenshot shows AISAD missing after the quota-only label update.

## Goal and relevant context

Restore a real visible two-line lowercase claude/codex weekly-remaining status label, keeping natural text spacing and the existing menu/cards. Source: MenuBarStatusLabel, SwiftUI MenuBarExtra entrypoint, user screenshot and fresh PID 81848 sample.

## Constraints and out of scope

No Control Center/system/signing/network settings, credentials, commits/pushes, dashboard or provider-collection changes. Preserve the existing scene identity and snapshot isolation. No agents.

## Done when

Normal startup reaches the app delegate and provider collection, status registration is unblocked, startup CPU/memory remain bounded, and the two-line contents are natively checked. Actual desktop visibility needs user confirmation.

## Verification

Baseline sample saved in output/status-label-startup-fix/before-startup.sample; build with ./script/build_and_run.sh --build-only; focused native text previews; fresh installed process path, startup logs, Control Center host logs and bounded memory sample; git diff --check.

## Baseline evidence

- User screenshot disproves the prior visibility claim.
- PID 81848 is alive, but has no normal-startup/provider logs.
- sample shows main-thread updateButton/setImage/setTitle cycling during SwiftUI app launch; footprint 10.1 GB after several minutes.
- Control Center retains AISAD's own allowed record and has no AISAD link in the disabled Codex group. No preference repair is indicated.

## Proposed correction

Avoid rendering a new SwiftUI ImageRenderer result during status-label evaluation. Use an AppKit text template image cached by the two displayed quota strings, and remove the label's TimelineView. Provider/store updates already supply quota changes.


## Fresh result

- Removed runtime ImageRenderer and TimelineView from the label. The normal app delegate owns a small AppKit template-image cache; unchanged displayed values retain the same NSImage identity. The label remains only two naturally spaced lowercase quota lines.
- Installed binary matches the build. Normal PID 13157 reached the app delegate at 16:35:33 MSK and refreshed all three providers at 16:35:35.
- Control Center accepted PID 13157, created a menu-bar displayable and requested visibility. Existing allowed associations were inspected only; no settings were changed.
- Fresh sample after several minutes: physical footprint 29.2 MB, peak 29.4 MB, main thread predominantly waiting for events. The prior sample was 10.1 GB and still cycling through launch-time image updates.
- Normal-process logs at 16:38:39 and 16:38:45 show the usage menu appearing and disappearing. No automated native UI interaction was used.
- 44 Swift tests passed. An isolated probe of the actual cache class verified 1,000 unchanged reads reuse the same object, changed values replace it once, and template height stays 20 pt.
- Native light/dark previews for normal 0%/75% and cached ~0%/~100% were inspected under output/status-label-startup-fix/; text remains readable and unclipped.
- Build, source review and git diff --check passed. The user was asked asynchronously to confirm actual desktop text visibility; no answer received yet.
- One verification lesson: process existence, visibility preference and offscreen previews do not establish successful menu-bar startup; require a normal app-delegate event, real status-host registration and bounded resource evidence.


## Desktop confirmation

The user explicitly confirmed that both claude/codex lines appeared in the menu bar: "Да, появились". Actual visibility is now confirmed in addition to the fresh startup, rendering, resource and test evidence. No remaining work for this fix.
