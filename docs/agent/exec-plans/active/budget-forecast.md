# Frozen weekly and monthly spend forecast with a suggested budget

- Status: implemented on branch feat/budget-forecast, awaiting review and merge
- Source: user request (2026-10-09) to design an automatic monthly budget suggestion from past spend
- Last updated: 2026-10-09

## Goal

When switched on, AISAD forecasts the next week's and month's known spend from local history and shows a
suggested monthly budget (a high quantile of the forecast). Each forecast is fixed for its whole period and
recomputed only when the period rolls over. All numbers come from a deterministic Python script; no LLM.

## Decisions (confirmed by the user)

- Calibration means three complete weeks of accumulated history already on disk, not three weeks after
  switching on. Local traces usually provide this immediately, so the first forecast and the self-backtest
  can run on the first day.
- The switch only displays the suggestion. `budget.json` changes only through `budget --set`.
- Explicit carve-out in a new ADR 0002: a statistical "forecast and suggested limit" is allowed; workflow
  advice, hypothetical savings and routing suggestions stay removed (commit 9f6031a). README, SKILL.md and
  CHANGELOG wording that says recommendations are disabled must be narrowed accordingly.

## Relevant context

- `terminal_chart_insights` (agent_usage.py) is the existing forecast. It averages observed days only and
  multiplies by every remaining day, so idle days are ignored.
- Costs are recomputed from raw traces on every run, so history is restated when prices change. A frozen
  forecast must therefore store its own inputs and outputs.
- Persisted state lives under `--output` (`budget.json`, schema_version 1). Writes use `atom_json`. There is
  no locking in the collector.
- ADR 0001: Python owns all aggregation; the Ink UI receives numbers and generated strings only.

## Research evidence (backtest on the author's real local history, private data not stored)

Rolling-origin backtest, 32 weekly origins, 7 calendar months, 29 rolling 28-day windows. Values are relative.

- Point accuracy is low for every method: weekly WAPE 0.67-0.70, monthly 0.77-0.84. The exponentially
  weighted weekday profile, the weekly-level method, EWMA and their combination are indistinguishable.
  The class is stably better than trailing means, last-week naive and the PR #9 method, with or without the
  largest outlier month.
- The PR #9 method is biased high: +20% weekly, +54% when the outlier month is removed.
- Quantile recipes: log-scale spread with Student-t inflation reached 69% weekly and 57% monthly coverage at a
  nominal P80, and 81-91% weekly at a nominal P90. Scaling the weekly spread down by sqrt(weeks) for the
  month dropped P90 monthly coverage from 86% to 57%, so month spread is not shrunk. Multiplying a point
  forecast by the empirical quantile of its own past ratio errors gave 74-88% coverage at a nominal P80 and
  needs at least six closed periods.
- Freezing costs little: the day-1 monthly forecast error is about the same as re-forecasting after week 1.
  Re-forecasting only wins from week 3 because it includes accumulated actuals. Hence a separate pace figure.
- Caveats: one user, many methods compared (winner's curse), few independent months. No ranking among the
  close methods is claimed; the choice rests on bias, robustness and simplicity.
- Literature used: FPP3 (short series, intervals, bias adjustment, cross-validation), M4/M5, forecast
  combination, Hyndman-Koehler MASE, conformal prediction (Angelopoulos-Bates, EnbPI, ACI), Gneiting
  (quantiles), forecast stability (Godahewa et al.), AWS/GCP/Azure/FinOps forecasting practice. Cloud
  providers re-forecast continuously and none freezes, so freezing is this project's own design choice.

## Specification

Target quantity: known priced cost per calendar day, summed over Claude and Codex, all pools, independent of
display filters (as the budget bar). Grok reported costs are excluded.

Day semantics for the forecast:

- A day with at least one priced request: its known subtotal.
- A day on or after `history_coverage.first_date` with no requests: $0 (idle). This differs deliberately from
  the PR #9 projection and must be documented in ACCOUNTING.md.
- A day whose requests are all unpriced: missing, excluded from the profile, and counted in coverage.
- Days before the first observation: missing.

Periods: weeks are Monday-first (as the statusline); months are calendar months in `--timezone`. A period's
forecast uses only days strictly before its first day, so it is a pure function of history and can be
computed lazily at any later run with the same result.

Point forecast (weekday profile, no trend, no optimised parameters):

- Weights `w = 0.5 ** (age_days / 14)` over up to the last 84 days.
- Per-weekday weighted mean, shrunk to its class (Monday-Friday or Saturday-Sunday) with `kappa = 2` in
  effective-weight units.
- Forecast = sum of the weekday means over the actual days of the target period. Means, not medians or
  trimmed values, so totals add up.

Suggested budget: quantile `q` (default 0.8, configurable) of the monthly total.

- Uncalibrated (fewer than 6 closed own periods): `F * exp(t_q(k-1) * s * sqrt(1 + 1/k) - s^2 / 2)`, where `s`
  is the shrunk standard deviation of log weekly totals over the last 8 complete weeks (floor 0.35, prior
  weight 4). No sqrt(weeks) reduction for the month. Label it uncalibrated.
- Calibrated (at least 6 closed periods, preferably 10): `F * quantile_q` of past `actual / forecast` ratios
  (floored at a small amount), over a rolling window of about 26. Label it with the measured hit rate.
- Weekly and monthly quantiles are computed separately; never multiply one by the other.

Gating: refuse with a reason string below 3 complete weeks, below 10 active days in the last 21 days, or
when the window has no priced spend. Confidence is low at 3-4 weeks, with a weekday with fewer than 2
observations, with a sharp recent level change, or when less than 80% of window requests are priced.
Medium at 5-8 weeks; high at 9 or more weeks with at least 4 closed own periods.

Implementation notes (deviations from the first draft of this plan):

- Calibration replays the same method on earlier Monday origins (newest 26, `forecast_ratios`) instead of reading
  closed ledger entries, so it is reproducible and available on day one. The ledger still records each closed
  period's actual for an accuracy summary.
- The suggested budget is never below the point forecast (`max(forecast, target)`).
- Instead of a P90 notice the output says when month-to-date or week-to-date already exceeds the target.
- Chart and statusline do not show the forecast yet; only `forecast`, `budget --forecast on|off` and
  `budget --quantile Q` exist. Wiring strings into the Ink UI is a follow-up.
- On the maintainer's history the replayed monthly ratios included an outlier month, which made the monthly
  target several times the forecast. This is reported, not tuned away.

Frozen state: `<output>/forecast.json`, `schema_version: 1`, keyed by period (`week:YYYY-MM-DD`,
`month:YYYY-MM`). An entry holds frozen_at, as_of_date, timezone, collector VERSION, price basis, method
parameters, input coverage, the point forecast, the suggested budget, its calibration state, and the closed-period
actual with error once the period ends. Create an entry only if absent; never overwrite. Do not store it in
derived files that are rewritten each run. Writing happens in `main()` or a helper, not in the pure report
function. Closed entries feed calibration and an accuracy summary.

Pace (separate, labelled field, never replaces the frozen number): month-to-date actual plus the frozen
profile over the remaining days. Show the percentage against the frozen forecast. If month-to-date exceeds the
frozen P90 before month end, show a one-time notice without changing frozen values.

CLI (proposal): `budget --forecast on|off`, `budget --quantile 0.8`, and a `forecast` command (JSON and text)
that skips network refresh like `budget`. The setting lives in `budget.json` next to the limit. The statusline
and Ink UI only render strings and numbers produced by Python.

## Constraints

- Statistics only; no hooks, polling, background jobs, network access or transcripts.
- Python 3.9 stdlib, one portable file; Windows, macOS and Linux CI.
- Costs are API-equivalent estimates, not invoices. Missing and unpriced days are never silently zero.
- Synthetic fixtures only; real reports stay private.

## Done when

- The forecast is deterministic, frozen per period, survives price restatement, and is skipped with a clear
  reason while uncalibrated.
- Tests cover gating, idle versus missing versus unpriced days, month edges (28-31 days), a level shift,
  frozen create-if-absent, rollover, calibration switchover, and the synthetic backtest range.
- ADR 0002, README, SKILL.md, ACCOUNTING.md and CHANGELOG are updated consistently.

## Verification

- `python3 -m unittest discover -v`, `scripts/build_release.py`, and in `ui/`: `bun run check`, `bun run test`.
- A seeded synthetic generator (weekday profile, AR(1) level, bursts, zeros, a level shift) asserts bias within
  bounds and a nominal P80 hit rate within a stated range, with fixed seeds.
- Local run against real history for sanity only; nothing from it is committed.

## Out of scope

- Writing `budget.json` automatically; a statusline bar based on the suggestion.
- Trend terms, per-provider or per-project budgets, holiday modelling, token-versus-price decomposition.
- Releasing a version.

## Open risks

- Pricing gaps: a growing share of unpriced requests lowers known spend and biases the forecast down. Coverage
  is shown and lowers confidence, but the forecast cannot repair missing prices.
- Level shifts (new model or workflow) are not visible until rollover; pace and the P90 notice mitigate this.
- Uncalibrated quantiles under-cover in both synthetic and real checks; the label and the self-measured hit rate
  are the mitigation.
- A newly added provider has little history and is gated by the combined series, not on its own.
- Re-pricing changes past actuals, so accuracy figures are approximate.

## Verification evidence

- 2026-10-09: 129 Python tests pass (12 new in test_forecast.py, including a seeded synthetic backtest range);
  `scripts/build_release.py` builds; touched files parse as Python 3.9. A live run on real history in a
  temporary output directory created `forecast.json` once and a second run left it unchanged.
- Not run locally: Python 3.9 interpreter, Windows, Playwright browser tests, Bun UI jobs (CI covers them; no
  UI files changed).

## Next step

Review, then decide whether to show the forecast in the chart/statusline and Ink UI.
