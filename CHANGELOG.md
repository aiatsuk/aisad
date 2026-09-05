# Changelog

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
