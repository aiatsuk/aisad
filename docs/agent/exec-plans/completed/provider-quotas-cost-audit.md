# Provider subscription limits and cost accuracy

- Status: completed
- Source: User request on 2026-10-22: live Claude, Codex and Grok quotas plus cost audit
- Last updated: 2026-10-22 12:34 MSK

## Goal

Show provider-reported subscription quota windows in the macOS menu, including five-hour and weekly windows when supplied, reset countdowns, freshness, automatic refresh and a manual refresh action. Audit the existing API-equivalent cost calculation against real trace schemas and published rates; correct verified defects.

## Relevant context

- agent_usage.py: normalized usage, deduplication, pricing, Grok reported turn costs.
- macos/Sources/AISADCore and AISADMenuBar: existing local collector and compact menu.
- Existing uncommitted changes on feat/macos-menubar belong to the ongoing user task.
- Official provider documentation and installed CLI protocol/schema are authoritative for quota adapters.

## Constraints

- Preserve existing changes, daily whole-dollar status label and calendar budget semantics.
- Keep subscription quotas distinct from dollar estimates.
- Never log or persist credentials, transcripts or authentication response bodies.
- No changes to certificates, keys, signing, network settings, provider configuration or login state.
- Read existing authenticated clients or credentials only for the exact provider usage read, without exporting secrets.
- No commits, pushes or installation outside the existing local development bundle.
- Missing, expired or inaccessible data must remain explicit; never synthesize quota percentages.

## Done when

- Supported provider sources are implemented and exercised on this machine.
- All three providers have explicit available/unavailable/stale states and per-window resets.
- Refresh behavior is bounded, cancellable and resilient to one provider failing.
- Verified pricing defects are fixed with regressions, and audit limitations are documented.
- Native light/dark previews, relevant tests and local bundle launch pass.

## Verification

- python3 -m unittest discover -q
- swift test --package-path macos
- Synthetic adapter fixtures: missing auth, malformed responses, stale/reset data and partial provider failures.
- Aggregate-only live quota and cost checks; no secret output.
- Native snapshots for available, loading and unavailable states; final raw diff and git diff --check.
- ./script/build_and_run.sh --verify

## Out of scope

Changing provider plans, purchasing credits, login/logout, credential refresh flows, charging API model calls, new OS services, historical billing reconstruction, publication.

## Current status

Completed. All three live sources, native layouts, failure/expiry/cooldown states, automatic refresh and cost regressions are verified. The final local app bundle is running.

## Completed

- Confirmed Codex has an installed stdio app-server and Grok/Claude CLIs are present.
- Confirmed the saved public price catalog was fetched on 2026-10-22.
- Established the distinction between five-hour/weekly subscription limits and API-equivalent dollar estimates.

## Next step

None. Ready for user review; no commit or push was performed.

## Decisions and rationale

Use actual provider windows and percentages; do not infer subscription quotas from tokens or dollars. User explicitly requested periodic updates in the running app.

## Failed approaches

Direct Security.framework reads from Python stalled. Moved Claude into a bounded worker and used the system credential reader for the exact existing Claude item; this succeeded without changing Keychain or login state. Simplified a Swift height expression after the compiler rejected its complexity. Native previews exposed unnecessary blank space, then a ViewThatFits sizing issue; ordinary lists now use intrinsic height and long lists use a bounded scroll viewport.

## Verification evidence

- Python baseline: 152 passed; after quota/cost regressions: 170 passed.
- Swift: 23 passed, including graceful cleanup and hard termination deadlines.
- Real Codex and Grok RPC quota reads succeeded. Claude OAuth read succeeded, including the observed limits[].weekly_scoped Fable schema.
- Published price refresh succeeded: 58 models, 2026-10-22.
- Aggregate live audit: 37,131 observations priced; zero token/cost-part/range invariant failures. 576 assumed standard tiers and 3,281 explicit internal-model price aliases remain estimation caveats.
- Grok: 207 reported turns, one incomplete; costIsPartial is now respected.

- Real minute refresh completions observed for the same process at 12:18:58, 12:20:03 and 12:21:07 Europe/Moscow.
- Final full verification: Python 170 passed, Swift 23 passed.
- Audit report: docs/agent/reports/provider-quotas-cost-audit.md.

## Open risks

Claude/Grok usage surfaces can change upstream. API-equivalent dollar values retain explicit standard-tier and internal-model assumptions; Grok reported totals remain separate. Real keyboard/VoiceOver interaction was not automated; native layouts and the actual read/refresh pipeline were verified.

Final checks: git diff --check and script syntax passed; raw collector/helper changes reviewed; ./script/build_and_run.sh --verify passed after the final build.
