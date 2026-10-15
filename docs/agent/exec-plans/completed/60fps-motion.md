# 60→120 fps terminal motion

- Status: delivered in PR #14 (release 1.3.0).
- Base: main at 6064898 (PR #13).

## Contract
Goal: at least 55 fps during month transitions in a real terminal.
Constraints: no new runtime dependencies, no Ink fork, unchanged accessibility modes, exact settled output, PTY suites green.

## Findings
- The 34 ms clock capped motion at ~29 fps.
- Four independent `useAnimation` subscribers (plot, text fade, amount roll, minimap) were aligned to different start times, so Ink's shared timer fired several times per period and frame gaps scattered from 8 to 24 ms.
- CPU profile: ~40% of time in Ink's `Output.get` (tokenize → styled chars → `styledCharsToString`/`diffAnsiCodes`) for the whole screen every frame. Ink's floor is ~4.7 ms per frame here even with no plot; ~16–20 ms on the user's VM.
- Coarser color quantization and fewer Text nodes did not move the ceiling.

## Changes
- `clock.tsx`: one shared clock, first 16 ms (60 fps), then 8 ms (120 fps) on request; Ink throttle 240 fps.
- `rows.tsx`: one pre-styled string per row via Ink's chalk; memo by string.
- `screen.tsx`: slot registration plus a line-diff writer inside `CSI ?2026 h/l`; full repaint on size/color change. Screen readers keep Ink rendering.

## Evidence
- Container PTY: 61–62 fps, gap p50 16.1 ms, p90 16.8–17.2 ms; text fades use ease-out so the first frame follows the key press; ceiling ≈235 fps with a 4 ms clock.
- User's arm64 VM, same synthetic data: installed build 9–29 fps (gap p50 34–101 ms); new build 56–61 fps (gap p50 16.2–16.4 ms).
- 45 Bun tests, 129 Python tests, `pty_motion.py` (6 modes), `pty_first_frame.py`, `build_release.py --with-ui`.

## Field recording follow-up
- User recording (1.2.0, ≈170×58): ≈15 fps, 67 ms median repaint gap; noisy mid-morph cloud; flickering dimmed labels.
- Cell-level diff + minimal SGR + 16-step color quantization: 8.9 → 4.2 KB and 528 → 306 SGR codes per frame at 170×58.
- Coherent wave (delay noise 4%, near-constant hop/lift); graph text sweep only on view open.
- Real-data check (user's parse cache, read-only via SQLite mode=ro; 4,317 trace files, 12 months, Grok absent because ~/.grok was not mounted): rank matching flew particles across half the plot on sparse months. Particles are now matched per provider by day (±1.8% of plot width, order-preserving); unmatched old dots sink and dissolve, unmatched new dots grow from $0 using a hidden half of a 2× particle pool.
- Real data, arm64 VM, 170×58: installed 1.2.0 ≈24 fps (15.8 frames per transition, gap p50 36 ms, 7.0 KB/frame); new build ≈62 fps (40 frames, gap p50 16.0 ms, p90 17.3–17.7 ms, 3.2 KB/frame).

## 120 fps follow-up
- Clock 8 ms, Ink throttle 240 fps; cells cached per row identity (`fitRow` keeps fitting rows), identical lines skipped.
- Real data, arm64 VM, 170×58: ≈121 fps (78.6 frames per transition), gap p50 8.0 ms, p90 9.6–9.7 ms; 1 ms-clock ceiling ≈495 fps (container ≈750 fps).

## Transfer fidelity on real data
Metric script over all 11 consecutive transitions of the user's months (170 columns):
- One-to-one same-column matching: start/end frames matched 100%, but only 37–75% of new dots came from on-screen particles; 25–63% of old dots dissolved and new ones grew from $0.
- Transfer planner (`planMorph`, 64 x-bins per provider, ±8 bins reach): new dots are moved 19–65%, split from on-screen dots 30–73%, from $0 0% in 8 of 11 transitions (Oct→Sep 31%: September days after the current date have no October neighbours). Old dots kept 65–100%; dissolved only where the provider is absent (e.g. Claude unavailable in August).
- A shared y-axis width removed the 1–2 cell shift between months; the first morph frame now covers 100% of the shown plot in all 11 transitions.
- Merged duplicates collapse after each morph, so the hidden half of the 2× pool stays free for splits.
