---
name: asi-ultraanalyze
description: Analyze every Claude Code session over a period or all time - a dashboard plus concrete examples of where another model or effort would have fit better.
argument-hint: "[7d | 30d | all | YYYY-MM-DD..YYYY-MM-DD]"
---

# ASI ultra-analyze

Show model and effort use across sessions and explain where a different choice would have been better, following the guide "Which Claude model should you build with?" (claude.dev, 2026-11-09). The script does the reading and the arithmetic; you read its examples and judge them. No model or effort is set on this skill on purpose: a one-turn model switch would re-write the session's cache.

## Steps

1. Turn the argument (`$ARGUMENTS`) into period flags: `7d` or `30d` is `--days 7` or `--days 30`; `A..B` is `--from A --to B`; `all` is `--all-time`; no argument means `--days 30`. Dates are `YYYY-MM-DD`.

2. Get the findings and the examples behind them, with a 10-minute timeout (all time can take a few minutes on the first run; later runs use a cache). With the period from step 1 in place of `--days 30`:

   ```sh
   python3 "${CLAUDE_SKILL_DIR}/../../scripts/asi.py" fit --days 30 --json --include-titles
   ```

   If the placeholder reached you unfilled, use this skill's base directory in place of `${CLAUDE_SKILL_DIR}`.

3. Build and open the dashboard for the same period:

   ```sh
   python3 "${CLAUDE_SKILL_DIR}/../../scripts/asi.py" dashboard --days 30 --open
   ```

   It prints the path of the HTML page and opens it in the browser. Its "Model fit" tab holds the charts behind the findings.

4. Read the JSON: the findings, the examples behind each, and the breakdowns by task class and by session. For each finding, look at its examples and decide whether the heuristic class is believable from what was asked and the signals. Drop or correct examples that are clearly misjudged, and say when a finding rests on weak examples.

5. Report in plain words:
   - the period, total estimated spend, and the split by model, by effort, and between main threads and subagents;
   - five to eight findings, largest first. For each: what happened, two or three concrete examples (date, what was asked, the model and effort that ran, the better choice), why the guide says so, and the rough saving or risk;
   - three actions, ranked by effect, that the user could take (for example a default effort, a model passed to a kind of subagent, compacting before a break);
   - the dashboard path as a link, with a pointer to its "Model fit" tab.

## Rules

- Change nothing: no settings, no agent files. Offer changes; the user decides.
- Main threads are judged per session, because a model switch re-writes the cache; subagents are judged per run; effort is judged per turn, because changing effort keeps the cache.
- The guide is a starting point. Where the user's own measurements say otherwise (for example reviewers kept on a stronger model after an A/B), say both and let the measurement win.
- Savings are upper bounds on API-equivalent estimates, not invoices: a smaller model or lower effort can need more turns.
