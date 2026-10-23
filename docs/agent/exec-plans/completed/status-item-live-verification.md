# Restore AISAD status item and verify live quota popovers

- Status: completed
- Source: User requests to repair the icon, reinstall AISAD and verify real hover, 2026-10-22
- Last updated: 2026-10-22 14:05 Europe/Moscow

## Goal

AISAD stays running with its menu-bar icon visible; real pointer interaction opens Claude/Codex/Grok quota cards with the existing ring and detail semantics.

## Relevant context

AISADMenuBarApp/AppDelegate, SnapshotExporter, run script and ProviderLimitsView. The original normal app used MenuBarExtra without insertion binding; app-level Menu Bar permission was enabled, but the scene was removed. Earlier UI and pricing changes remain uncommitted and preserved.

## Constraints

No certificate, key, signing or network configuration changes. No commits/pushes. Preserve provider cooldowns, collectors, usage history and budget. The user separately approved the exact Control Center association repair and its restart. No other app permissions were changed.

## Done when

Fresh installed app survives collection with its icon visible. User confirms real hover/cards/pointer transfer/click pinning/Escape. Swift checks, installation verification, raw diff review and runtime logs support the result.

## Verification

swift test --package-path macos; ./script/build_and_run.sh --build-only; bash -n script/build_and_run.sh; git diff --check. Verify installed binary hash, process executable path, Control Center host registration, native visibility preference and real user quota-card logs. Exercise isolated snapshot export while the visible normal app stays running.

## Out of scope

Dashboard, pricing, provider adapters, new runtime menu architecture, global permission resets, publication.

## Current status

Completed. Installed /Users/aiatsuk/Applications/AISAD.app, normal PID 43516. Visibility is 1 and Control Center creates the menu item without blocking it. User confirmed the requested live card scenarios with "норм"; normal-process logs show appearances/dismissals for all three providers and click pinning.

## Completed

- Added explicit insertion ownership so removal does not automatically terminate the app.
- Added limited OSLog for lifecycle/menu/card appearance, dismissal, pointer entry and pinning; no usage payloads or credentials.
- Found a QA isolation bug: exporting snapshots as another SwiftUI App registered a competing hidden status host with the same bundle/item identity and displaced the normal host.
- Added AISADLauncher: export uses a plain AppKit event loop/AppDelegate without constructing the SwiftUI App/MenuBarExtra scene. Normal runtime stays SwiftUI.
- Snapshot script mode no longer kills the normal app.
- Compared earlier working entrypoint/run script; preserved the quota UI instead of introducing a new status-item/popover runtime.
- Rebuilt a fresh generated bundle, preserved the previous one, installed and registered only ~/Applications/AISAD.app, and verified executable hashes match.
- Found the actual visibility block in Control Center trackedApplications: AISAD's own record had isAllowed=true, while AISAD was also in the disabled com.openai.codex group's menuItemLocations.
- Prepared a backup/dry-run, obtained explicit user approval, removed exactly one AISAD association from that disabled group, verified all other 45 records and other preference keys unchanged before restart, then restarted Control Center and the installed AISAD.
- Confirmed the repaired association stays absent, AISAD remains enabled, icon visibility is 1 and provider refreshes continue.
- User performed real hover/card checks; normal PID runtime logs confirm all three providers appeared and closed, with Claude/Codex pin actions. Escape and pointer-transfer behavior are user-confirmed.

## Decisions and rationale

Keep the normal SwiftUI runtime. The failed native insertion retries did not address the stored Control Center association. Fix the exact association rather than enabling Codex or resetting all menu-bar preferences.

Export snapshots without ever registering a status host. isInserted=false alone still registers a scene and is insufficient isolation. A snapshot process's view-appearance logs must never count as live menu verification; filter runtime evidence by the normal PID.

## Failed approaches

App preference visibility reset, explicit insertion alone, one startup insertion retry, clean reinstall alone and launching through Finder alone did not remove the stored disabled-group association. The automatic retry was removed. The initial diagnosis that the app-level Menu Bar toggle was off was disproven by the user's screenshot; do not repeat that advice for this case.

A full NSStatusItem/NSPopover runtime migration was considered but not implemented after the user requested investigation of the working version and reinstall.

## Verification evidence

- 42 Swift tests passed, 2026-10-22 13:56 MSK; output/status-item-live/reinstall-tests.log.
- Final build and fresh bundle staging passed; reinstall-build.log and clean-package-build.log.
- Installed binary SHA256 matches generated binary; installation.json. Old generated bundle retained under previous-20261022T105817Z/.
- Isolated export 13:57 MSK rendered light/dark successfully without Control Center status-host events for the export PID.
- User-approved repair 14:02 MSK: registration-repair/applied.json and local before-apply backup. Exactly one association changed; no other permission/settings changes.
- Control Center 14:02 MSK requested visibility for the unblocked host; new normal PID 43516 registered an actual menu displayable. Native visibility stayed 1.
- Installed process path confirmed /Users/aiatsuk/Applications/AISAD.app/Contents/MacOS/AISADMenuBar.
- Background isolated export while normal PID 43516 was visible completed; visible-isolation/ contains the rendered files, visibility stayed 1 and the same normal PID survived.
- Real user activity 14:03 MSK: live-hover.log filtered only normal PID 43516 shows main menu, Claude/Codex/Grok card appearances/dismissals and pin events. Provider refreshes continued through 14:04 MSK.
- User response to all-three-provider hover, pointer transfer, click pinning and Esc scenario: "норм".
- Final source/whitespace review, bash syntax and git diff --check passed.

## Next step

Use the installed ~/Applications/AISAD.app. No more launch/visibility retries or monitoring required.

## Open risks

No remaining blocker for this task. Native mouse actions were performed by the user, not automated. VoiceOver and unrelated dashboard visual checks were not part of this verification. Control Center association backup and diagnostic logs are local ignored artifacts, not repository or memory content.
