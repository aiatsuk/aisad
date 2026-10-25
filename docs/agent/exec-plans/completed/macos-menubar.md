# AISAD macOS menu bar

- Status: completed
- Source: user request and menu bar screenshot, 2026-10-22
- Last updated: 2026-10-22 Europe/Moscow

## Goal
An optional native macOS menu bar app shows today's and calendar-week spending in USD,
plus calendar-month spending, the existing monthly budget and its progress.

## Relevant context
Python owns pricing and aggregation in agent_usage.py. budget.json stores monthly_budget_usd.
The installed CLI uses ~/.local/share/aisad/output (AISAD_DATA_DIR overrides the data root).
ADR 0001 keeps business calculations in Python. The native companion is an optional SwiftPM package.

## Constraints
Preserve CLI/Linux behavior and existing budget/forecast settings. No daily/weekly limits.
Use local Claude/Codex data only. No network, login items, signing changes, credentials,
commits or pushes. Run the native app only while explicitly launched.

## Done when
Native menu and monthly-budget settings work, all three calendar periods are correct,
unknown/partial pricing remains explicit, app builds and relevant tests pass.

## Verification
Baseline and final: python3 -m unittest discover -q.
Backend: python3 -m unittest test_menubar -v.
Native: swift test --package-path macos; ./script/build_and_run.sh --verify.
Inspect native light/dark snapshots and a live aggregate report. git diff --check and raw diff.

## Out of scope
Provider subscription quotas, daily/weekly limits, auto-launch at login, distribution/signing,
release publication, web/terminal redesign and forecast changes.

## Current status
Implemented and locally launched from dist/AISADMenuBar.app on feat/macos-menubar; changes remain uncommitted.

## Completed
Added calendar aggregate JSON command and installed-skill forwarding.
Added native menu, shared monthly settings, timed/cancellable collector client and explicit refresh ownership.
Added build/run entry point and CI job. Reviewed native Light/Dark captures and the raw changes.

## Next step
User review of the running local app; publication is outside this request.

## Decisions and rationale
Calendar week starts Monday; all periods use the report timezone and include all sessions/pools.
The monthly budget is shared with CLI, not another preference or provider subscription quota.
The optional accessory app refreshes every five minutes and on demand; quit stops its task.
Ship the existing collector in the local app bundle; call it directly without skill auto-updates.

## Verification evidence
2026-10-22, base 7076765:
- Baseline: python3 -m unittest discover -q: 136 passed.
- Final Python suite: 143 passed, including 7 menu bar period/pricing checks and installed CLI forwarding.
- swift test --package-path macos: 13 passed, including real-collector shared-budget preservation
  on synthetic history, bounded output, timeout, cancellation and malformed reports.
- ./script/build_and_run.sh --verify: build passed; AISADMenuBar process running.
- Native NSHostingView captures inspected in Light/Dark under output/menubar-final (ignored).
  Actual local aggregates loaded with the saved 2000 USD monthly budget; no real budget writes performed.
- git diff --check passed; tracked and untracked raw changes reviewed.

## Open risks
Python 3.9+ is a runtime prerequisite. Keyboard/VoiceOver and minimum-OS execution were not
manually verified; local build/run used Swift 6.2.1 on macOS 26.4.1 with a macOS 14 deployment target.
Snapshots render the real native content tree, not a desktop capture. Remote CI has not run.
