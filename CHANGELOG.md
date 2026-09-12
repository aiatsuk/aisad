# Changelog

## 1.1.2 — 2026-09-10

- Add `prices --refresh`: read current published rates from models.dev into a local catalog, revalidated with the stored ETag. Reports use it when present and name their basis in `price_as_of`, `price_basis` and `price_sources`.
- Keep what the published source omits. Base rates, context tiers and fast-mode rates are imported; one-hour cache writes and flex/batch discounts keep their built-in values, a model the source drops keeps its built-in rate, and models it publishes that AISAD did not know about are added. On this device the import reproduced every built-in rate exactly and priced 30 observations that had no rate before.
- Read only the `anthropic` and `openai` providers, so a reseller entry cannot shadow a first-party rate. Refuse an oversized response, a payload without first-party models, or rates the pricer would reject, keeping the last good catalog in each case.
- Refresh from the launcher at most once every 24 hours, next to the existing update check; `--offline` or `AISAD_AUTO_PRICES=0` disables it and a failure never blocks a report. Commands that read sessions still make no network requests.

## 1.1.1 — 2026-09-09

- Answer `usage`, `analyze` and `statusline` from usage observations alone. They no longer merge the event timeline, derive session evidence, republish `sessions.sqlite` or rewrite `usage.json`; on a 7GB local history one report drops from about 3.5 minutes to under 10 seconds. Reported totals, breakdowns, comparisons and diagnostics are unchanged.
- Update `sessions.sqlite` incrementally: only sessions whose traces changed size or mtime are rewritten, while a different collector version, parser or price catalog still rebuilds every row. Add the missing index on each foreign key, without which deleting one session scanned whole child tables.
- Split cached parse results so a usage run loads observations without decoding event payloads. Rows written by 1.1.0 are split on first read rather than reparsed; the parser is unchanged, so no trace is read again.
- `collect`, `sessions`, `session`, `dashboard` and `--include-events` still publish the evidence database and `usage.json`. Refresh evidence with `collect` when usage runs are the only thing that has run.

## 1.1.0 — 2026-09-07

- Read chronological Codex `thread_settings_applied` tier changes so recorded Fast usage is priced correctly; invalidate cached parser results. Add processing-tier evidence and accounting regression checks.
- Label the token-weighted metric as Cache rate, expose its percentage in JSON, and prominently identify synthetic demo figures. Document the accounting audit and comparable tools.
- Replace dashboard spend-pool cards with uncached input, cache-read, cache-write and output token/cost breakdowns. Expose cache-write cost ranges by component in the UI and JSON.

- Add a transactional local SQLite event database with usage observations, session/turn relationships, tool-call metadata, context observations and file/line provenance.
- Add one-shot `collect`, `sessions` and `session` commands with JSON, date/provider/model filters, descendant scope and timeline pagination.
- Add chart-to-session drill-down, request evidence, recorded lifecycle/compaction events and measured/estimated/unavailable definitions to offline reports.
- Preserve existing usage and pricing fixes from 1.0.7. Usage JSON stays schema 2; the additive evidence database/report uses schema 1.
- Remove continuous collection, the HTTP watcher, browser polling and status-hook input. `--watch` and `--stdin` now fail before collection; `statusline` remains a manual one-shot command. Existing external hooks/schedulers are not modified.
- Keep recommendations, raw conversation storage and tool instrumentation disabled. The optional skill invokes the standalone collector on demand.


## 1.0.7 — 2026-09-06

- Compare known priced cost subtotals even when other requests lack prices. Remove unknown-cost suffixes, disclose exclusions separately for both periods, and retain all usage/token records. Periods without priced data remain unavailable.
- Keep Codex message/tool coverage on the session that observed telemetry when a file switches sessions. Show previous-period pricing-gap details when the current period is fully priced. Invalidate the parser cache.
- Exclude replayed parent usage before a fork's first local turn context, restore the fork owner after inherited metadata, and invalidate the parser cache. Preserve uncertain files without a turn boundary and report them in collection diagnostics.
- Show saved usage totals before JavaScript initializes and retain them when scripts are disabled or initialization fails.
- Compress large embedded snapshots losslessly to reduce offline HTML size; loading uses no external files or network requests.
- Add current calendar week (Monday through the snapshot date) and previous calendar week (Monday–Sunday) dashboard presets. Compare the current partial week with the same weekdays last week.
- Preserve the last explicit Codex model when repeated metadata resumes the same session, and invalidate the parser cache. New sessions and unrecorded models remain unknown.
- Label current prices as applying to all dates, expose observed history coverage and missing registered traces, and include separate Grok completed-turn statistics with provider-reported costs.
- Compact filters: keep period and provider visible, show dates only for custom ranges, and fold secondary filters behind a counted toggle.
- Keep overview cards inside their tab so Sessions, Context and Cache open directly below the filters.
- Shorten period comparison and move coverage explanations and pricing gaps behind details. Reduce the footer to version, update time and concise data notes.
- Add published Standard API rates for GPT-5-Codex, GPT-5.1-Codex, Mini, Max and GPT-5.2-Codex. Internal auto-review, unidentified models and unsupported processing modes remain unpriced.
- Explain partial estimates with a filtered model/reason/token breakdown and a known-subtotal label. Add pricing coverage to usage JSON and preserve pricing status in request statistics.

## 1.0.1 — 2026-09-05

- Focus AISAD on collecting and displaying usage statistics. Remove the recommendation engine, findings, hypothetical savings, routing suggestions and status-line coaching.
- Keep weekly comparisons, provider/model filters, session timelines, context and tool counts, cache usage, cost components and spend pools. The dashboard now has four views.
- Keep `analyze` as an alias for `usage`. JSON schema 2 replaces `diagnostics` with `telemetry` and `analysis_records` with `request_stats`, removes `analysis_rules`, and omits status-line coaching. Existing usage totals and breakdown fields are unchanged.
- Update skill instructions, documentation, synthetic demo and README screenshot. Installation and automatic updates retain their existing behavior.

## 1.0.0 — 2026-09-05

- Establish 1.0.0 as the stable version baseline, retaining the complete local dashboard, usage CLI, diagnostics and installable Codex/Claude Code skill.
- Keep daily GitHub release checks, verified automatic updates, explicit check/update commands and offline operation.
- Add an explicit `install --allow-downgrade` option for the one-time transition from the earlier 2.x labels. Preserve local modifications and reports; automatic updates still reject downgrades.
- Invalidate cached update decisions after a reinstall so a pending release from the previous installation cannot undo the version reset.

Earlier 2.x numbers were assigned during implementation. Their history is retained below; new releases proceed from 1.0.0.

## 2.4.0 — 2026-09-05

- Rebuild the dashboard with public Uber Base Web design conventions: Overview, Recommendations, Sessions, Context & tools, and Cache health views, global filters, session timelines and a dark theme.
- Add eight documented local checks for model routing, initial context, tool payloads, sustained context growth, possible cache rebuilds, long-context tariffs, premium modes and polling. Separate associated spend from conditional savings; avoid overlapping savings in the total.
- Derive numeric tool/MCP statistics from traces without exporting messages, payloads or arguments. Expose telemetry coverage and keep unpriced findings explicit.
- Add `analyze` text/JSON reports and `statusline` with session/provider/pool estimates, context/cache counters, coaching, terminal watching and Claude Code stdin integration.
- Support optional shared interactive and separate managed budgets with visible 50/80/100% nudges. Explicitly tagged managed sessions propagate to confirmed descendants.
- Update the installable skill, synthetic demo, README screenshot and cross-platform/browser regression coverage.

## 2.3.1 — 2026-09-05

- Lead quick `usage` reports with estimated API cost and compact input/output token counts.
- Compare estimated cost, input and output with the previous period. Keep exact token counts, requests and sessions in JSON.
- Update the skill's response format and README examples.

## 2.3.0 — 2026-09-05

- Add `usage` for a fast weekly text report without HTML or a running server.
- Add `usage --json` with equal-length period comparisons, provider/model/project/role filters, grouped metrics, and optional normalized request records.
- Add an installable AISAD skill for Codex and Claude Code, including local analysis instructions and the standalone collector.
- Check for stable GitHub releases once daily when the skill is used; update instructions, helper and collector together. Support explicit checks, offline use and offline installation.
- Verify release and file checksums, preserve local edits and reports, and restore the previous installation after a failed replacement.
- Publish versioned standalone and skill assets from tested Git tags. Keep runtime dependencies limited to Python's standard library.

## 2.2.0 — 2026-09-05

- Remove payment tracking and billing CSV import. Show API-equivalent usage estimates only.

## 2.1.0 — 2026-09-05

- Default to the last seven calendar days and compare with the preceding period where records exist.
- Add provider breakdowns and consistent filters across both periods.

## 2.0.0 — 2026-09-05

- Publish the English local Claude Code and Codex dashboard, portable collector, synthetic demo and screenshot.
