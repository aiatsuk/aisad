# Terminal morph transitions

- Status: implementation complete; delivered in PR #10
- Branch: feat/terminal-morph-motion
- Base: PR #9, commit 5ccf136; separate stacked PR requested on 2026-10-08.

## Contract
Goal: brief morph transitions for month navigation, a real-data footer minimap in both views, readable exact amounts and responsive keyboard input.
Context: optional upstream Ink 8 UI, aggregate-only Python reports, attached Terminal Motion Engine architecture. Use the existing renderer and its shared animation clock.
Constraints: no extra dependencies, renderer fork, network, hooks, background collection or personal-data publication. Bounded palette and particle arrays; only active transitions consume clock ticks. Keep Python fallback, snapshots and statusline static. Respect reduced motion, screen readers and ASCII. Preserve the unrelated usage audit.
Done when: transitions are deterministic, interruptible, clipped, resize/exit safe, final text exact; separate PR contains animation-only changes over #9.
Verification: Bun typecheck/tests/build, full Python suite and checked package; PTY input/resize/reduced-motion/idle/cleanup; synthetic visual frames and bounded frame-time measurements.
Out of scope: SVG/fonts, native Ink host elements, spring/timeline framework, infinite loops, agent-monitor scenes and changes to price/budget calculation.

## Decisions
Use bounded normalized particles for the main plot and interpolate corresponding provider/day samples for the footer minimap. The minimap shows actual calendar-month daily costs, thin connected provider curves, a shared monthly peak scale, blank gaps and unpriced markers; newly present samples fade in place. Keep exact axes, prices and table cells as text. Prepare transitions before commit to prevent target flashes, use a 360 ms quintic curve, and retarget from the visible pose. Upstream Ink exposes useAnimation; a 34 ms motion clock has margin against a 17 ms render throttle. Group adjacent styles, memoize stable rows and avoid per-cell objects on ordinary animated plot rows. Resize settles geometry; narrow terminals use a 16-cell rather than 20-cell minimap. No renderer fork or claim of zero Yoga work.

## State
Initial delivery: PR #9 has 14 successful GitHub checks. The new motion implementation passes 117 Python tests, strict TypeScript checks, 21 Bun tests (125 assertions), bundle/package checks and six synthetic built-UI PTY scenarios. Published as [PR #10](https://github.com/aiatsuk/aisad/pull/10), stacked on #9. GitHub CI validates each pushed revision. That initial delivery preceded the local minimap and pacing follow-up.

## Evidence and limits
- Built UI tested with real PTYs: W/H/L, rapid retargeting, resize 110x30 to 80x24, exact weekly totals, no leftover plot/table particles, Q, Ctrl+C=130, and exact terminal restoration.
- Active, reduced motion, ASCII, no color and screen-reader modes passed. External fetch/socket operations were blocked; the bundled data URI for Yoga remained allowed.
- Idle output stays quiet; animations use Ink's shared clock only while active. Plot geometry settles on resize and multi-panel/missing-data plots remain static.
- Synthetic ANSI frames exported through actual Ink; no personal data in the preview.
- Local 512-particle measurement: core p95 approximately 0.02 ms and colored static Ink frame p95 approximately 25 ms. This excludes terminal flush/scheduler latency and is not a cross-platform FPS guarantee. Existing renderer still performs React/Yoga work for changed grouped text cells.
- Observer feedback: model CSI E/F next-line commands before judging terminal artifacts. Captured synthetic bytes showed Ink relies on these commands; final settled-screen checks pass with them modeled.
- Linux CI exposed a timing assumption: the initial animation clock emitted ten frames, but navigation produced no dirty Braille cells inside the fixed 90 ms sample. The test now waits for an emitted navigation frame before interrupting, with a bounded deadline within the transition, and independently requires multiple initial animation-clock frames.
- The new bundle also passed private real-aggregate PTY checks at 80x24 with H/L/W, resize and terminal restoration; those data remain local.

## Minimap and pacing follow-up — 2026-10-09

Goal: publish the locally installed minimap, first-frame fix and responsiveness changes in the existing PR #10.
Relevant context: actual Ink renderer/clock code, aggregate-only UI contract, synthetic PTYs and private local aggregate validation.
Constraints: preserve accounting, static modes and unrelated usage audit; stage no private data, bundles or reports. Keep the PR stacked on #9; no merge or release publication.
Verification: strict TypeScript, 30 Bun tests (182 assertions), 117 Python tests, rebuilt UI/package/release-version checks, all six PTY modes and the atomic first-frame regression. Earlier local checks also verified installed manifests, offline launcher/fallback, unchanged budget and real aggregates at 80x24. The local pacing probe measured maximum frame gaps decreasing from about 167 ms to 61–98 ms; these are machine-specific observations, not an FPS guarantee. `ui/test/pty_performance.py` reproduces the synthetic probe.
Done when: this follow-up is committed and pushed, PR #10 describes the final minimap/motion behavior and its remote head matches the local commit.
Out of scope: usage history audit, budget/pricing changes, merge and release.

## Next
Review PR #10 and its current checks. Retarget its base to main after PR #9 merges.
