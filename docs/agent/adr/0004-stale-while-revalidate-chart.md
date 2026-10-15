# ADR 0004: Stale-while-revalidate interactive chart

## Context

The interactive chart needed a full collector snapshot (about 2 s on a large real history) before its first frame. Most launches show nearly the same aggregates as the previous launch.

## Decision

The collector saves the UI dataset to `output/chart-ui.json` with a key of version, options and color level. A matching launch writes it with `stale: true`, starts the UI and computes the snapshot on a daemon worker thread. The fresh dataset replaces the UI's input file atomically; the UI polls that file every 60 ms only while stale. `mergeDataset` keeps unchanged months by identity and gives changed months a new `revision`, which is part of the motion key, so they play an ordinary morph and amount roll. Fresh data keeps the selected month, or follows the new initial month if the user has not navigated.

R repeats the same path on request: the UI (only when the dataset carries `refresh: true` and nothing is pending) writes `refresh.request` next to its input and marks itself stale; the collector polls for it every 50 ms while the UI runs and starts one worker at a time. A failed collection republishes the shown dataset without the stale mark and is reported on exit.

Quitting before the refresh ends returns the shown month's cached report and abandons the worker; parse-cache writes are uncommitted and roll back. Without a matching cache the start is unchanged.

## Consequences

- First frame no longer depends on history size; numbers can be stale for about 2 s, marked "Updating…" in the footer.
- The cache contains only the aggregates the UI already receives (no traces, paths or projects).
- Python and the UI must agree on `stale`, `refresh` and `revision`; `parseDataset` validates them.
