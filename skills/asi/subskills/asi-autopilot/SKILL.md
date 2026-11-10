---
name: asi-autopilot
description: Switch ASI autopilot on or off - model and effort chosen for each subagent and workflow agent; the main session's model is left alone.
argument-hint: "on | off | status [session]"
---

# ASI autopilot

With autopilot on, you pick the model and effort for each subagent and workflow agent by the guide "Which Claude model should you build with?", instead of letting them inherit the session's model. The main session's own model is never switched automatically: a switch re-writes the whole cache, so there you only suggest. For the same reason this skill sets no model or effort of its own: a one-turn model switch would re-write the session's cache.

The argument is `$ARGUMENTS`. No argument means `status`.

## on

```sh
python3 "${CLAUDE_SKILL_DIR}/../../scripts/asi.py" autopilot on
```

This saves the rules in the ASI block of `CLAUDE.md` (in `CLAUDE_CONFIG_DIR`, by default `~/.claude`), so new sessions start with autopilot on, and prints the rules. Follow the printed rules in this session from now on. Then tell the user in two or three lines what will now happen and that `/asi-autopilot off` undoes it.

## off

```sh
python3 "${CLAUDE_SKILL_DIR}/../../scripts/asi.py" autopilot off
```

Removes the autopilot rules for new sessions. The first-message hint is a separate switch (`rules on|off`) and is not touched. In this session, stop choosing models and effort for subagents on ASI's behalf from now on.

## status

```sh
python3 "${CLAUDE_SKILL_DIR}/../../scripts/asi.py" autopilot status
```

## on session / off session

Only this session, nothing saved: for `on session` run `python3 "${CLAUDE_SKILL_DIR}/../../scripts/asi.py" autopilot show` and follow the printed rules until the session ends; for `off session` stop following them.

If the `${CLAUDE_SKILL_DIR}` placeholder reached you unfilled, use this skill's base directory in its place. If the command reports a problem with the markers in `CLAUDE.md`, show the message to the user and change nothing by hand.
