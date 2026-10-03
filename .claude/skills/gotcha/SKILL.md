---
name: gotcha
description: "Capture a learning/gotcha or a mid-session note and push it to the dsp-session-logs repo RIGHT NOW. Trigger: /gotcha, gotcha, ye note kar le, isko learning mein daal, session log kar de."
user-invocable: true
---

# gotcha — capture a learning to the self-learning log NOW

The `SessionEnd` hook already logs full telemetry when the session ends. Use `/gotcha` to capture a
learning or note **mid-session** — e.g. the moment something breaks, a new gotcha is found, or a
session won't reach a clean end. Write it and push it immediately.

1. **Resolve the logs repo**: `SESSION_LOGS_REPO` from `config/paths.local.json` (or env
   `DSP_SESSION_LOGS_REPO`). If it's not configured, tell the user (see SETUP.md) and stop.
2. **Compose a short Markdown note**: the user's gotcha/note **verbatim**, plus 2-3 lines of context —
   which client / stage, which tool or subagent, what went wrong or what was learned, and (if useful)
   the fix. **Never include raw tool outputs, PII, or tokens** — summaries only.
3. **Write** to `<SESSION_LOGS_REPO>/logs/<YYYY>/<MM>/<YYYY-MM-DD_HHMMSS>_gotcha_<implementer>.md`
   (implementer = `git config user.name`).
4. **Push**: `git -C <repo> pull --rebase --autostash` → `git add <file>` → `git commit -m "gotcha: <1-line>"`
   → `git push`. Retry once on a push conflict. Then tell the user it's pushed (give the filename).

Keep it fast and small — this is a quick capture, not the full session report. The end-of-session hook
handles the telemetry; `/gotcha` handles the human insight in the moment.
