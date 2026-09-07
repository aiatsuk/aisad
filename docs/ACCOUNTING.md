# Usage accounting

Reviewed against provider documentation and comparable tools on September 7, 2026.

AISAD reads existing local records when invoked. It counts recorded usage observations, not user prompts or unique pieces of text. Reusing the same cached prefix on ten model calls legitimately contributes ten cache reads. Repeated delivery or copied history of the same observation must be deduplicated.

## Token categories

| Source | Total input | Uncached input | Output |
| --- | --- | --- | --- |
| Claude Code | `input_tokens + cache_read_input_tokens + cache_creation_input_tokens` | `input_tokens` | `output_tokens` |
| Codex | `input_tokens` | `input_tokens - cached_input_tokens - cache_write_input_tokens` | `output_tokens` |

The normalized input categories are disjoint: uncached input + cache reads + cache writes = total input. Input + output = total processed tokens. Codex reasoning output is already part of output and must not be added again. Cache-write usage is read when recorded; it is never inferred from context growth or a pause.

Claude's definitions are documented in [prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching). OpenAI's [cache usage examples and write/read pricing](https://developers.openai.com/api/docs/guides/prompt-caching) show that cached and written tokens belong within input. The [Codex token protocol](https://github.com/openai/codex/blob/0e9589ffae082437e6793e8c24900e876dfdf86a/codex-rs/protocol/src/protocol.rs) distinguishes latest usage, cumulative counters and context-window bookkeeping.

## Cache rate

`cache rate = sum(cache-read tokens) / sum(total input tokens)`

This is a token-weighted read rate, not the average of per-request percentages, the percentage of requests with any hit, or the fraction of context currently occupied. Cache writes are included in the denominator but not the numerator. The JSON retains `cache_share` as a fraction and additionally exposes `cache_read_rate_percent`; empty input produces null.

## Cost

For each observation, sum the uncached-input, cache-read, cache-write and output components using that model's applicable rates and recorded processing mode. Add recorded billable tool charges separately. Five-minute and one-hour Claude writes use their respective rates; unrecorded TTL produces a range. Current prices come from [OpenAI](https://developers.openai.com/api/docs/pricing) and [Claude](https://platform.claude.com/docs/en/about-claude/pricing).

Codex can record mode changes in `event_msg/thread_settings_applied`. A recorded `priority` or legacy `fast` value applies to subsequent observations; a recorded `default` restores Standard. Unrelated settings do not reset the last tier. Unknown explicit tiers remain unpriced. Unmarked history uses the existing, disclosed Standard assumption; AISAD does not apply the current global configuration retroactively. Fast multipliers come from the model's price rule, not a universal assumption about every model.

Version 1.1.0's accounting audit fixed a missing reader for these settings events. Before that fix, Fast observations without a tier in `turn_context` were priced as Standard. Token counts and cache rates were unaffected. The parser cache version is incremented so old parsed records are refreshed.

These amounts are API-equivalent estimates, not subscription charges or provider invoices. The bundled catalog applies its rates to every date; it does not reconstruct historical discounts. Use dated price overrides for known historical rates. Unknown models/modes are excluded from cost and identified; their recorded tokens remain included.

## Deduplication and counters

- Claude: use message identifiers to coalesce streamed updates and copied history; retain one coherent input snapshot and final/max output. SDK cumulative cost reports remain separate.
- Codex: use `last_token_usage` for a recorded usage observation. An unchanged consecutive cumulative counter identifies a repeated snapshot. A reset begins a new sequence. Recognized fork prefixes are excluded before counting the child's local usage; unresolved fork boundaries are reported.
- Cumulative counters must not be summed as if each value were a new request. A delta can also include history imported into a session or a bookkeeping reset, so it must not blindly replace an available per-request observation.
- Current AISAD does not recover observations when `last_token_usage` is absent; it reports `quality.codex_missing_last_usage`. Missing logs cannot be reconstructed. Counts represent observed records, not a guaranteed count of every provider API request.

## Comparison with other tools

| Tool/source inspected | Accounting choices |
| --- | --- |
| [ccusage Codex parser](https://github.com/ccusage/ccusage/blob/f748ae59436bb9f26aabad2820d086c54749603d/rust/adapters/codex/src/parser.rs) | Prefers latest-request usage when available and cumulative counters have advanced; falls back to cumulative subtraction. Reads chronological tier settings. |
| [ccusage Claude parser](https://github.com/ccusage/ccusage/blob/f748ae59436bb9f26aabad2820d086c54749603d/rust/adapters/claude/src/daily.rs) | Adds input, cache-read, cache-creation and output fields; uses message/request identity and sidechain handling for duplicates. |
| [Token Use Codex documentation](https://tokenuse.app/docs/development/tools/codex/) | Prefers cumulative deltas and uses latest usage as a fallback; deduplicates by session lineage. |

These tools establish useful cross-checks, not an invoice oracle. Results can differ because of source discovery, date boundaries, identity/fork rules, latest-versus-cumulative preference, model fallback and pricing assumptions. ccusage also supports stored-cost versus recalculated-cost modes; compare equivalent modes and dates ([cost modes](https://ccusage.com/guide/cost-modes)). This review inspected documentation and source; it did not upload local logs or run another tool's installer.

## Comparing snapshots

Use the same device, source files, dates, timezone, provider/model filters, price catalog and processing modes. The rolling seven-day window changes daily. Newly saved files can add older observations. README screenshots are synthetic examples and cannot be compared with personal reports.

An audit should independently sum raw usage fields after deduplication, reconcile input buckets and cost components, test repeated counters/resets/streaming/forks, and inspect missing-price and source-coverage diagnostics. Browser totals should then reconcile with the resulting JSON and SQLite observations. No hooks, background polling or tool instrumentation are required.
