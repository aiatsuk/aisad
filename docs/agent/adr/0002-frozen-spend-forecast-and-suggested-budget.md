# Frozen spend forecast and suggested budget

- Status: accepted
- Date: 2026-10-09
- Decision source: user asked for a statistics-only weekly and monthly forecast with a suggested monthly budget, and chose an explicit carve-out from the no-recommendations rule.

## Context
Version 1.0.1 removed the recommendation engine, findings, hypothetical savings, routing suggestions and statusline coaching so that AISAD only collects and displays usage statistics. The existing shared-budget forecast averages observed days only, so idle days are ignored and it overshoots (about +20% weekly on the maintainer's history).

## Decision
Allow one narrow kind of derived number: a deterministic Python forecast of known spend for the current Monday-Sunday week and calendar month, plus a suggested budget (a configurable quantile of the forecast, default 80%). It is off by default and switched with `budget --forecast on|off`; `budget --quantile Q` sets the quantile.

- It is a statistical projection, not advice: no workflow checks, no savings scenarios, no model or routing suggestions, no LLM.
- It never changes the saved limit. `budget --set` remains the only writer of `monthly_budget_usd`.
- A period's forecast uses only days before the period starts, so it is a pure function of local history. It is written once to `forecast.json` beside `budget.json` and never overwritten during the period; the period's actual is added after it ends.
- A separate "pace" figure (actual to date plus the frozen weekday profile for the remaining days) is shown beside, never instead of, the frozen forecast.
- Idle days count as $0, wholly unpriced days and days before the first observation are missing. Fewer than three complete Monday-Sunday weeks or ten priced days in the last 21 refuse to forecast.
- Method, defaults and evidence are in `docs/ACCOUNTING.md` and `docs/agent/exec-plans/active/budget-forecast.md`.

## Consequences
README and SKILL.md wording about disabled recommendations must name this exception. Forecast accuracy on short, bursty history is low and the quantile can be wide; the output states calibration, confidence and pricing coverage. Everything remains local, on demand, without hooks, polling or network access.
