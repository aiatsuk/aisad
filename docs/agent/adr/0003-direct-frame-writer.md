# Direct frame writer for the Ink dashboard

- Status: accepted
- Date: 2026-10-12
- Decision source: user required at least 55 fps terminal motion.

## Context
Ink rebuilds the whole screen on every frame: it re-tokenizes every text node into styled characters and diffs SGR codes per character, even for unchanged lines. With a 34 ms clock the dashboard peaked at about 29 fps. On an arm64 Linux VM on the user's Mac, Ink alone took 16–20 ms per frame (median), so frames arrived 34–100 ms apart. Several independent `useAnimation` subscribers also fired at offset moments and produced uneven frames.

## Decision
Keep Ink for input, raw mode, the alternate screen, resize events and teardown. Outside screen-reader mode, the dashboard's Ink tree renders nothing visible: components register rows into named slots (`main`, `minimap`), and `ScreenWriter` composes the screen after each commit, compares it cell by cell with the previous frame and rewrites only changed runs with absolute cursor positioning inside one synchronized update (`CSI ?2026 h/l`). Color codes come from Ink's own chalk instance, so 16/256/truecolor downsampling is unchanged, but a code is emitted only when the style changes (no per-segment close/open pairs, spaces never switch style). Lit plot colors are quantized to 16-unit steps. A single shared 8 ms motion clock (≈120 fps) drives every animation; Ink's throttle is 240 fps. Cells are cached per row object and identical lines are skipped, so unchanged axes, labels and legend cost nothing per frame.

Screen readers keep Ink's normal text rendering.

## Consequences
Per-frame cost is now mostly our own composition: about 4 ms here (≈235 fps ceiling) instead of ≈10 ms through Ink. Transitions run at the clock rate: about 61 fps with a 16–17 ms p90 frame gap in the container, and 56–61 fps on the VM where Ink managed 9–29 fps. The writer must own every visible cell: a size or color change triggers a full repaint, and Ink's empty output never overwrites it. All dashboard glyphs are single-cell; `fitRow` cuts by code point. PTY tests still model the emitted escape sequences.

## Field recording — 2026-10-12
A screen recording of the 1.2.0 build in the user's terminal (≈170×58 cells) repainted only 9–13 times per 650 ms transition (≈15 fps, 67 ms median gap). Mid-transition frames read as a dot cloud: per-particle start, hop and lift noise scattered neighbours, and dimmed axis labels flickered at that rate. Bytes matter as well as CPU: at 170×58 the line-level writer sent ≈8.9 KB and ≈530 color codes per frame; the cell-level writer with minimal codes sends ≈4.2 KB and ≈300. Labels now switch instantly between months (amounts still roll); the text sweep plays only when a view opens. PTY tests read the modelled screen, because unchanged cells are no longer resent.

## 120 fps — 2026-10-13
The user asked for 120 fps. With the clock at 8 ms and per-row cell caching, the user's real data on the arm64 VM (170×58) runs at ≈121 fps: 78.6 frames per 650 ms transition, median gap 8.0 ms, p90 9.6 ms (timer jitter). A 1 ms clock shows the ceiling: ≈495 fps there (≈2 ms per frame) and ≈750 fps in the container. Output is ≈330 KB/s only while a transition runs; idle output stays zero.
