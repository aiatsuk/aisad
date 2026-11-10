---
name: asi-suggest
description: Suggest the Claude model, effort and modes for the task in this conversation, with reasons and the cost of switching now.
argument-hint: "[a task to judge instead of this conversation]"
---

# ASI suggest

Say which model, effort and modes fit the work in front of the user, based on the guide "Which Claude model should you build with?" (claude.dev, 2026-11-09). This skill names no model or effort of its own on purpose: it must run on the session's model, because a one-turn model switch would re-write the whole cache.

## Steps

1. Get the facts with one command:

   ```sh
   python3 "${CLAUDE_SKILL_DIR}/../../scripts/asi.py" suggest --session "${CLAUDE_SESSION_ID}"
   ```

   If those two placeholders reached you unfilled, use this skill's base directory in place of `${CLAUDE_SKILL_DIR}` and leave out `--session` and the session id. The output gives the current model and effort, the context size, what a switch would cost right now, a heuristic class per recent turn, and the guide table.

2. Classify the task yourself. You have the conversation; the heuristic only counted tools and files. Judge the work that is still ahead, not the work already done. If the user passed a task as an argument (`$ARGUMENTS`), judge that task instead. When the task is unclear, the guide's answer is Opus at medium.

3. Reply in this shape, in plain words, without a preamble:

   - **Task:** the class and one line on what makes it that class.
   - **Suggested:** model, starting effort and the effort to raise to; then modes that apply (plan mode before a large change, fast mode only for latency-sensitive interactive work on Opus or Fable, Haiku or Sonnet subagents for search, logs and summaries, a lead with parallel workers only when the work is bigger than one context, run at low and re-run failures at high when results can be checked automatically).
   - **Now:** the current model and effort, and whether that fits, is more than needed, or may fall short.
   - **Why:** two or three reasons with numbers from the guide table.
   - **Switching:** only when you suggest a different model. Give the one-time re-write cost from the command output, and the cheaper route: `/compact` first, or a new session opened with a short written plan. A smaller model also cannot read the bigger model's earlier reasoning. Changing effort keeps the cache, so suggest that first when it is enough.
   - **If it falls short:** add a self-check, then raise effort one step, then go one model up at a lower effort.

## Rules

- Do not change the model or effort yourself, even where a tool for it exists. The user switches.
- Do not recommend a switch for a little remaining work: say the current setup is fine to finish on.
- Costs are API-equivalent estimates from local transcripts, not invoices. Say so once if you quote dollars.
