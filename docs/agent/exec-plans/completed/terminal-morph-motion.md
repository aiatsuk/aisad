# Terminal morph transitions

- Status: implementation complete; delivered in PR #10
- Branch: feat/terminal-morph-motion
- Base: PR #9, commit 5ccf136; separate stacked PR requested on 2026-10-08.

## Contract
Goal: brief morph transitions for month navigation and graph/week changes, preserving readable exact amounts and keyboard responsiveness.
Context: optional upstream Ink 8 UI, aggregate-only Python reports, attached Terminal Motion Engine architecture. Use the existing renderer and its shared animation clock.
Constraints: no extra dependencies, renderer fork, network, hooks, background collection or personal-data publication. Bounded palette and particle arrays; only active transitions consume clock ticks. Keep Python fallback, snapshots and statusline static. Respect reduced motion, screen readers and ASCII. Preserve the unrelated usage audit.
Done when: transitions are deterministic, interruptible, clipped, resize/exit safe, final text exact; separate PR contains animation-only changes over #9.
Verification: Bun typecheck/tests/build, full Python suite and checked package; PTY input/resize/reduced-motion/idle/cleanup; synthetic visual frames and bounded frame-time measurements.
Out of scope: SVG/fonts, native Ink host elements, spring/timeline framework, infinite loops, agent-monitor scenes and changes to price/budget calculation.

## Decisions
Use a small React-independent typed-array engine with normalized points, spatial Morton matching, easing and reusable Braille buffers. A compact footer badge morphs between graph/week shapes and navigation arrows. Graph lines morph inside their plot region for month navigation; axes, prices and table cells remain plain exact text. Upstream Ink exposes useAnimation, not the proposed fork's RawAnsi; use bounded grouped text cells through the existing renderer, making no claim of zero Yoga passes. Resize settles chart geometry; the normalized badge keeps its transition.

## State
Baseline: PR #9 has 14 successful GitHub checks. The new motion implementation passes 117 Python tests, strict TypeScript checks, 21 Bun tests (125 assertions), bundle/package checks and six synthetic built-UI PTY scenarios. Published as [PR #10](https://github.com/aiatsuk/aisad/pull/10), stacked on #9. GitHub CI validates each pushed revision. Existing installed targets stay on the independently tested #9 version.

## Evidence and limits
- Built UI tested with real PTYs: W/H/L, rapid retargeting, resize 110x30 to 80x24, exact weekly totals, no leftover plot/table particles, Q, Ctrl+C=130, and exact terminal restoration.
- Active, reduced motion, ASCII, no color and screen-reader modes passed. External fetch/socket operations were blocked; the bundled data URI for Yoga remained allowed.
- Idle output stays quiet; animations use Ink's shared clock only while active. Plot geometry settles on resize and multi-panel/missing-data plots remain static.
- Synthetic ANSI frames exported through actual Ink; no personal data in the preview.
- Local 512-particle measurement: core p95 approximately 0.02 ms and colored static Ink frame p95 approximately 25 ms. This excludes terminal flush/scheduler latency and is not a cross-platform FPS guarantee. Existing renderer still performs React/Yoga work for changed grouped text cells.
- Observer feedback: model CSI E/F next-line commands before judging terminal artifacts. Captured synthetic bytes showed Ink relies on these commands; final settled-screen checks pass with them modeled.
- Linux CI exposed a sampling flaw: inspecting only a 90 ms tail after a title discarded the same packet containing the transition. The test now captures the whole navigation event and independently requires multiple initial animation-clock frames. All six modes pass locally with CI build/runtime conditions reproduced.
- The new bundle also passed private real-aggregate PTY checks at 80x24 with H/L/W, resize and terminal restoration; those data remain local.

## Next
Review PR #10 and its current checks. Retarget its base to main after PR #9 merges.
