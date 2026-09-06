# Changelog

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
