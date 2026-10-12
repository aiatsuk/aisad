# Codex-grade terminal motion

- Status: implemented locally on branch `feat/codex-grade-motion`; not committed or pushed.
- Base: main at ddac585 (release 1.2.0).

## Contract
Goal: match the motion quality of the Codex CLI welcome mark (reference screen recording, 2026-10-12) in the Ink UI.
Reference: `codex-rs/tui/src/empty_state_animation/` (Apache-2.0): SDF extrusion, Y spin with X wobble, perspective, per-dot z-buffer, studio lighting, per-cell averaged truecolor, quintic easing, opacity fades. Technique only; no Codex/OpenAI marks or paths.
Constraints: unchanged from terminal-morph-motion. No dependencies, no infinite loops, exact final text, static accessibility modes, aggregate-only data.

## Decisions
- Animate real data rather than add a decorative logo intro.
- Review 1: a full 3D card turn between months lost the line morph. The morph is the base; Codex-style depth and light sit on top.
- 768 particles ranked by provider, then day, then value; rank i maps to rank i, so lines reshape instead of scattering. 2048 particles read as a solid cloud mid-flight.
- Review 2 ("more fancy"): arc paths (upward hop drifting in the navigation direction), 7% landing overshoot, a landing flash band, comet tails only above 1.5 dots/lag, a tilt of up to 14°.
- Review 4: sparks removed ("pollen around the graphs"); the flight curve stays.
- The wave is normalized to the occupied x span. Without it, Sep→Oct (8 data days) stalled about 120 ms before anything moved.
- Text and weekly cells sweep in by column in the same direction (30% floor on the graph, 15% on the table).
- Review 3: provider amounts roll. Only legend (`● Provider $X`) and budget (`Month $X / $Y · Z%`) segments are parsed and re-rendered, keyed by provider. Values start from the last visible amounts (retarget-safe), stagger by 70 ms-equivalents, glow while digits differ from the final text and return the original rows once settled.
- Review 5: plot height no longer depends on the month's maximum. Grid rows = height (TS and Python), steps 1/1.5/2/2.5/3/4/5/6/8/10; the Ink UI uses min fitted height across months.
- Lighting is normalized so a settled front face equals its provider tint. It assumes a dark background (#1b1b1b), as the existing minimap fade does; Ink cannot query the terminal background.

## Evidence
- `bun run check`, 42 Bun tests, 129 Python tests, `scripts/build_release.py --with-ui`.
- All six `pty_motion.py` modes and `pty_first_frame.py` pass.
- `pty_performance.py` locally: graph month morphs emit 18–21 frames over about 620 ms at about 33 ms intervals. Single gaps of 70–100 ms occur only at the quiet ease-in/out ends, where frames are identical and Ink writes nothing. These numbers are machine-specific.
