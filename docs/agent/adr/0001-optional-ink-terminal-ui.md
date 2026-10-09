# Optional Bun/Ink terminal UI

- Status: accepted
- Date: 2026-10-08
- Decision source: user chose a separate TypeScript/React/Ink interface.

## Context
The Python collector already owns pricing, calendar periods, shared budgets and portable reports. The dashboard needs component layout, keyboard navigation and live terminal resize.

## Decision
Keep collection and costs in Python. Pass aggregate-only monthly reports through a private temporary file to a strict TypeScript React UI using public upstream Ink. Use Bun to bundle dependencies into one module. Ink manages Yoga layout, input, resize and terminal teardown. Use upstream packages rather than proprietary Claude code.

Bundle the UI and third-party notices optionally in the existing checked release ZIP. Source fingerprints prevent packaging a stale UI build. Bun is an optional runtime: without it/the bundle, Python renders the portable dashboard. Snapshot and JSON commands never launch Bun. Keep the existing Python command parser; Commander, ripgrep and native addons add no necessary behavior here.

## Consequences
UI builds need pinned npm dependencies and Bun; local usage needs no package installation or network access. The embedded Yoga WASM loads from a data URI. Disable Ink's optional development-only DevTools gate while bundling. Keep separate layout tests and PTY checks for real input, resize and cleanup. Pricing remains authoritative in Python, including incomplete observations and the separate Grok cost basis.

## Weekly analytics extension — 2026-10-08
Keep weekly subtotals, daily intensity levels and deterministic budget/weekday insights in Python as well. The UI receives numeric totals/levels and generated message strings rather than calculating another forecast. See [accounting rules](../../ACCOUNTING.md) for windows, weighting, gap handling and the monthly budget reset.
