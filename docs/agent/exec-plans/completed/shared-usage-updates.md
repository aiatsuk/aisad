# Shared usage updates
- Status: completed
- Source: user request, 2026-10-23
- Goal: one successful local collection updates open CLI, menu-bar and dashboard usage views and the saved monthly budget.
- Context: agent_usage.py make_snapshot, terminal Ink parent/watcher, CollectorClient/UsageStore, offline HTML renderer.
- Constraints: local files only; no listener/server, signing/key/network changes, commits/pushes or provider-auth changes. Preserve filters, prior successful data, price coverage and evidence timestamps. Custom data roots/prices/timezones must not overwrite default shared state.
- Done when: updates propagate both ways without another scan; readers reject old/corrupt writes; shared budget propagates; stopped readers release resources; tests exercise cross-process and browser state transitions.
- Verification: baseline Python menu/telemetry and swift test; Python full suite, Swift tests/build, Bun check/test/build and PTY live tests; actual embedded dashboard JS and sidecar protocol with synthetic data; raw diff and whitespace review.
- Out of scope: provider quota scheduling, cloud history, pricing policy, week-layout changes and unrelated CI failures.
- Design: atomically publish a versioned normalized usage snapshot and compact menu report. Serialize publication and reject collections that started before the accepted revision. Readers follow file changes. The browser reads local script sidecars; evidence retains its independent collection timestamp.
- Current status: implemented and source reviewed; 185 Python, 51 Swift and 51 Bun tests passed. Calendar/pricing/loader/dashboard-state Node suites passed. Release and bundled CLI built. Actual isolated PTY accepted an external collector and budget update in 0.115 s.
- Next step: user opens a new CLI session or reloads the upgraded dashboard once; subsequent usage and saved-budget updates propagate automatically.

## Verification and decisions
- A single small local script is the atomic commit marker for Python, Swift and the browser. Prepared payloads are rejected until committed; the previous accepted payload is retained for recovery.
- Publication order is independent of collection start order. A budget edit cannot invalidate a newer in-flight collection.
- Lightweight refreshes preserve independently timestamped session evidence from the accepted snapshot.
- Initial new regression runs exposed over-escaped revision patterns; explicit ASCII digit classes fixed the validator. Calendar extraction was updated for the new header function.
- Browser callbacks, gzip payloads, stale/uncommitted generations, filters, active tabs and shutdown are tested with the shipped embedded JavaScript. No browser visual walkthrough or live file:// UI is claimed.

## Outcome
- Updated and relaunched the stable installed AISAD app without changing bundle identity, system preferences, signing or network configuration. Updated both installed Codex/Claude collector runtimes and the bundled terminal UI; backups are recorded in ignored output/shared-usage/install-*/install.json.
- Actual installed CLI publication was accepted by the running app: its usage-sync event matched the CLI and shared-state revision exactly. The saved dashboard was upgraded from the same accepted data. Evidence remains independently timestamped.
- Cross-process PTY verification passed: an open real CLI adopted an external menu collection and budget save, with 0.115 s measured delivery after publication. Existing PTY stale/R behavior also passed.
- Returning to a visible browser tab checks the local marker immediately. Plain standalone documents and explicit alternative-source experiments remain isolated.
- Final validation: 185 Python tests; 51 Swift tests; 51 Bun tests and TypeScript check; four Node suites; native Release and Bun bundle builds; both PTY scenarios; raw diff and whitespace review.
- Browser sidecar callbacks are tested using the actual embedded JavaScript, including gzip, commit gating, filter/tab preservation, corruption, visibility and shutdown. Native desktop GUI and browser file navigation were not automated or claimed as visual proof.
- No commit, push or merge performed by this task. Existing unrelated PR CI failures are outside this change.
