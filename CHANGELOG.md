# Changelog

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
