# Publish synchronized usage and finish PR 22
- Status: active
- Source: user request, 2026-10-23
- Goal: commit/push the completed cross-interface synchronization into existing PR 22, fix failing CI, and merge only when every current-head check is green and no blocking review remains.
- Context: feat/macos-menubar at ac1c757; shared-usage-updates.md; current GitHub check rollup and job logs.
- Constraints: preserve all in-scope work; explicit path staging, ordinary push and expected-head merge. No force push, branch deletion, hook bypass, signing/key/certificate/network configuration changes or external comments.
- Done when: synchronization and narrow CI corrections are committed, remote/PR heads match, full CI passes for that exact head, review threads are checked, GitHub confirms merged, and the local tree is clean.
- Verification: Python 3.9 and current Python suites; Swift test/build; Bun check/test/build and PTY shared scenario; embedded dashboard Node suites; full GitHub statusCheckRollup and fresh reviews before merge.
- Out of scope: new functionality, pricing policy, provider login changes, release/signing configuration, unrelated refactoring.
- Current status: original failures corrected; Python 3.9/current suites (185 each), Swift (51), Bun (51), Node suites, 17 headless dashboard scenarios and session-evidence browser regression passed locally. Desktop/mobile/offline demo capture, Release build, real shared-update PTY, raw diff and whitespace review also passed.
- Next step: commit and push to PR 22, then inspect every current-head check and review thread. Merge only the verified head after all checks succeed; the GitHub merge result is the completion evidence.

## Corrections
- Synthetic HTTP 304 now supplies a closable BytesIO body and checks cleanup; reproduced the original KeyError on Python 3.9 before the correction.
- SwiftUI header uses a separate view-builder boundary and concrete tooltip String to avoid the CI compiler's type-checking timeout.
- Incomplete pricing suppresses percentage comparisons; the browser expectation now preserves that semantic.
- A deterministic event gate replaces a race in the cached-chart test, discovered during concurrent local validation.
- Demo capture checks an explanatory no-results row and absence of clickable sessions, rather than requiring an empty tbody.
