# Instant chart cold start

Status: released in 1.4.0.

## Goal

`aisad chart` should show the dashboard at once, like the Codex CLI, instead of after the full trace scan.

## Measured baseline (1.3.0, user's real history, arm64 VM)

820 cached traces, 37,021 requests. First frame after 2.2–2.35 s. `make_snapshot` 1.73–1.92 s: cache read 0.56–0.73 s, registry 0.29–0.31 s, pricing 0.25–0.26 s, JSON decode 0.21 s, request statistics 0.13 s, report and dataset 0.13–0.15 s. Once a day the launcher also blocked on the GitHub update check and a models.dev refresh (timeout 60 s).

## Decisions

- Stale-while-revalidate (see [ADR 0004](../../adr/0004-stale-while-revalidate-chart.md)): open on the previous aggregates, rescan on a worker thread, replace the file the UI polls; changed months morph with a new revision, unchanged months keep identity.
- Daily network work runs in a detached `maintain` helper; updates apply from the next launch.
- Collector: one `SELECT path,fingerprint,payload` scan instead of 820 point queries, only the used registry columns, LRU caches for project and model names, price rules memoized per (catalog, model, UTC day).

## Result

- First frame 0.14–0.18 s (13× faster); fresh data at 1.74–1.96 s; quit before refresh 55 ms, no stray files.
- `make_snapshot` 1.56–1.63 s (−8%), dataset hash identical to 1.3.0 (`generated` excluded).
- R refresh: fresh numbers 1.62–1.75 s after the key press on the same history.
- Tests: 50 Bun tests, 133 Python tests, `pty_live.py`, `pty_motion.py`, `pty_first_frame.py`.

## Next

The scan itself is now off the critical path. Further gains need incremental aggregates per trace (skip unchanged traces' pricing and statistics), which changes the cache format.
