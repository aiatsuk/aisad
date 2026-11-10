---
name: asi-analyze
description: Analyze one Claude Code session turn by turn - which model and effort ran, and which would have fit better and why. Defaults to this session.
argument-hint: "[session id or prefix]"
---

# ASI analyze

Show where each model was used in a session and where another would have been the better choice, following the guide "Which Claude model should you build with?" (claude.dev, 2026-11-09). No model or effort is set on this skill on purpose: a one-turn model switch would re-write the session's cache.

## Steps

1. Run the analysis. With an argument, analyze that session; without one, this session:

   ```sh
   python3 "${CLAUDE_SKILL_DIR}/../../scripts/asi.py" fit --session "$ARGUMENTS" --include-titles
   python3 "${CLAUDE_SKILL_DIR}/../../scripts/asi.py" fit --session "${CLAUDE_SESSION_ID}" --include-titles
   ```

   Run only the line that applies. Add `--json` when you need every field. If the placeholders reached you unfilled, use this skill's base directory in place of `${CLAUDE_SKILL_DIR}` and leave out `--session` and the session id; the command then summarizes the recent period instead of one session, so say that in your report.

2. Read the output critically. Each main-thread turn and each subagent run carries the model and effort that ran, a heuristic class, the guide's model for that class, a verdict and a rough saving. The heuristic only counts tools, files and calls:
   - For the current session you know what each turn was really about. Correct a wrong class and say that you did.
   - Verdict `session` means a smaller model would have done that turn alone, but another turn in the same session needed the bigger one. That is not waste: a main thread keeps one cache, so its model is a per-session choice.
   - Verdict `under` is a quality risk. Check whether that work needed rework before calling it a problem.

3. Report in plain words:
   - one line of totals: cost, models and efforts used;
   - a short table of the turns that matter (skip trivial ones): what was asked, what ran, what the guide suggests, verdict;
   - subagents grouped by type, noting those that inherited the big model with no model passed;
   - the two to four most useful findings, each with the concrete turn or agent behind it, the better choice and the reason from the guide (include cache events: model switches, rewrites after idle gaps, calls above 200k of context);
   - what to do differently next time, at most three points.

## Rules

- Change nothing: this skill only reads transcripts.
- Savings reprice the same tokens on another model and apply the guide's effort ratios. A smaller model can need more turns, so present them as upper bounds, and as API-equivalent estimates rather than invoices.
