# ADR 0005: Model fit

- Status: accepted
- Date: 2026-11-10
- Decision source: the owner asked on 2026-11-10 to merge the model and effort advisor into ASI, including the dashboard. This reverses part of ADR 0002 for this one feature.

## Context

ADR 0002 and version 1.0.1 removed routing suggestions and hypothetical savings, so that ASI would only count and show usage. ADR 0002 kept one narrow exception, the spend forecast.

On 2026-11-09 Anthropic published a guide, "Which Claude model should you build with?" (claude.dev). It names a model and a starting effort for each kind of task, and it gives measured effort ratios for Opus. The owner had a prototype (AIR) that compares what ran in Claude Code with that guide. The public guide is a fixed reference, so the comparison is not ASI's own opinion about how to work.

## Decision

Model fit is in. It is a second kind of derived number next to the forecast, and it stays inside the existing rules: local, on demand, no network, no model calls.

- **What is judged.** Every main-thread turn and every subagent run of Claude Code is a unit. A heuristic puts the unit in one of the guide's task classes from what happened in it (tools, files edited, number of calls, a few keywords). The class gives the guide's model and effort; the model and effort that really ran give the verdict: `over`, `under`, `effort-over`, `effort-under`, `session` or `fits`. Codex is not judged.
- **Per session, per run, per unit.** A main thread keeps one cache, and a model switch re-writes it, so its model is judged per session, by the strongest model any substantial turn needed. A small turn in a session that also holds hard work gets `session`, which is not waste. A subagent has its own context, so it is judged per run. Effort keeps the cache when it changes, so it is judged per unit.
- **Savings are rough upper bounds.** They reprice the same requests on the guide's model through the collector's own price rules and apply the guide's effort ratios. A smaller model or a lower effort can need more turns, so every report says "upper bound" and "API-equivalent estimate".
- **The heuristic marks candidates.** It cannot see how hard the thinking was. A person, or a model reading the examples (`/asi-analyze`, `/asi-ultraanalyze`), checks them before anything is changed. The owner's own measurements win over the guide.
- **Rules and autopilot are instructions, not hooks.** `asi rules on|off` and `asi autopilot on|off` write one marked block into `CLAUDE.md` (`<!-- asi:begin -->` to `<!-- asi:end -->`) and touch nothing outside it. The block holds a first-message hint and, if switched on, rules for choosing a model and effort for each subagent. They are off until the user switches them on, and the installer does not switch them on. Autopilot never changes the main session's model.
- **Surfaces.** `fit`, `suggest`, a fifth dashboard tab, and four Claude Code sub-skills.

## Consequences

- ADR 0002 stays in force for everything else: no workflow checks, no savings scenarios outside model fit, no routing advice for Codex, and the forecast stays opt-in.
- Privacy is unchanged: no prompt text in reports or datasets, except the opt-in redacted title with `--include-titles`. Edited file paths are kept only as short hashes.
- The class table, the effort ratios and the prices come from the guide and the price catalog. They need updating when Anthropic changes the guide or the models.
- Capturing the facts changed the parser, so the first run after an update reparses every trace once.
- README and SKILL.md wording that says ASI makes no recommendations must name model fit as an exception.
