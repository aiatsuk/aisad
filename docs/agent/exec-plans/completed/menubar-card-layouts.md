# Menu-bar card layout exploration

- Status: completed.
- Goal: review three native menu-bar alternatives with Today/Week side by side and a larger monthly card containing the comparison chart and budget context.
- Relevant context: user's annotated screenshot, existing MenuBarView/SpendPeriod/SpendComparison, DEBUG MonthlyChartPreview and isolated SnapshotExporter.
- Constraints: retain exact existing period totals and matched-window comparisons. Daily chart keeps solid current versus dashed previous month; budget uses a separately labelled USD rail. Explore a clearly labelled cumulative alternative with a true budget threshold. System colors and native controls; synthetic data only.
- Done when: three layouts are rendered in both themes, one refinement iteration is checked, budget under/at/over-limit and missing/incomplete/error/large-value states are reviewed, and a recommended design is shown with alternatives.
- Verification: ./script/build_and_run.sh --build-only; actual Swift adapter checks for cumulative totals and gaps; native offscreen captures for each design and relevant state; final raw diff and whitespace review.
- Out of scope: installed app and normal status item, production data wiring, database-lock investigation, pricing/collector changes, live native hover proof, installation, commits/pushes, signing/network settings.
- Planned variants: A separate quiet cards (300 pt), B denser 280 pt layout, C 300 pt monthly cumulative chart with an in-plot budget line.


## Outcome

- Rendered three DEBUG-only native alternatives: A uses separate outlined cards with a daily chart; B uses denser cards at the existing 280 pt width; C uses a cumulative monthly chart with the budget threshold inside the plot.
- All variants keep Today/Week in one row and Month in a larger card. Existing SpendPeriod amounts and matched-window comparisons are reused. The chart remains aggregate Claude/Codex, solid current and dashed previous month.
- A/B budget rail is a separate USD scale below the day axis. Its tick marks the monthly limit; its dot marks known spend. Overspending extends the scale beyond the budget and marks the exceeded segment. C compares cumulative dollars directly to a labelled budget line.
- Synthetic over-budget fixtures exercise the three period cards and the monthly budget. Native menu/chart totals and day/week/month comparisons were verified from the actual CLI aggregation.
- Actual Swift adapter checks passed 10 states: under/at/over budget, empty, zero, unpriced, partial, large, gaps and error. Cumulative prefix sums and endpoints match daily totals and the monthly card; missing dates and gaps remain absent; unknown prices remain flagged.
- Final native light/dark snapshots cover 17 layout/state combinations, including seeded selected days, increased contrast, large values, missing/partial data and the database-lock error presentation. This verifies the prototype layout, not live pointer/keyboard interaction or a database-lock fix.
- Two refinement passes removed spare card height, increased the compact plot height, fixed equal card widths and comparison wrapping, and consolidated incomplete-price notes. The final under-budget and large-value labels were visually checked again.
- Final DEBUG bundle build passed (21.04 s). Raw diff and new-source whitespace review passed.
- Recommended starting point: B for the requested compact daily comparison. C is the alternative when progress toward the monthly budget is the primary task.
- Artifacts: output/menubar-card-layouts/cards/cards-comparison-{light,dark}.png; individual layouts in {cards,compact,cumulative}/; seeded hover state in selected/; adapter-tests.log and fixture-verification.json hold checks.
- No normal app/status-item changes, installation, live collection, pricing changes, commits/pushes, signing or network/settings changes.

### Final normal-state dimensions

- cards: 300 x 407 pt.
- compact: 280 x 371 pt.
- cumulative: 300 x 381 pt.
