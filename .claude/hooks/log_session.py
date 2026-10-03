#!/usr/bin/env python
"""SessionEnd hook for dsp-claude-core — the self-learning loop's data collector.

Reads this session's transcript, extracts TELEMETRY (tool calls + durations, subagent runs, errors,
duration, human turns) and the FLOW (gist of each human prompt), writes one Markdown log, and pushes
it to the dsp-session-logs repo. Also invoked by /gotcha for a manual mid-session log.

Design rules:
- FAIL-SAFE: never breaks session end. Any error -> write what we can / skip, always exit 0.
- PRIVACY: never includes raw tool OUTPUTS (prod-query results, PII, tokens) — only summaries.
Resolves the logs repo from env DSP_SESSION_LOGS_REPO, else config/paths.local.json["SESSION_LOGS_REPO"].
"""
import json, os, sys, subprocess
from collections import defaultdict
from datetime import datetime


def _run(args, cwd=None):
    try:
        return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=90)
    except Exception:
        return None


def _parse_ts(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


def main():
    try:
        raw = sys.stdin.read()
    except Exception:
        raw = ""
    hook = {}
    try:
        hook = json.loads(raw) if raw.strip() else {}
    except Exception:
        hook = {}

    transcript = hook.get("transcript_path") or ""
    session_id = str(hook.get("session_id") or hook.get("sessionId") or "unknown")
    cwd = hook.get("cwd") or ""
    reason = hook.get("reason") or hook.get("hook_event_name") or "SessionEnd"
    note = hook.get("_gotcha_note") or ""   # /gotcha passes a manual note here

    script_dir = os.path.dirname(os.path.abspath(__file__))
    logs_repo = os.environ.get("DSP_SESSION_LOGS_REPO", "")
    if not logs_repo:
        cfg = os.path.join(script_dir, "..", "..", "config", "paths.local.json")
        try:
            logs_repo = json.load(open(cfg, encoding="utf-8")).get("SESSION_LOGS_REPO", "")
        except Exception:
            logs_repo = ""
    if not logs_repo or not os.path.isdir(logs_repo):
        return  # not configured yet — skip silently

    # ---- parse transcript ----
    events = []
    if transcript and os.path.isfile(transcript):
        try:
            for line in open(transcript, encoding="utf-8", errors="replace"):
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except Exception:
                        pass
        except Exception:
            pass

    tool_uses = {}                      # id -> {name, ts}
    tool_counts = defaultdict(int)
    tool_durs = defaultdict(float)
    agent_runs = []                     # {type, dur}
    errors = defaultdict(int)
    user_prompts = []                   # gist of real human prompts
    first_ts = last_ts = None

    for ev in events:
        ts = _parse_ts(ev.get("timestamp", ""))
        if ts:
            if first_ts is None or ts < first_ts:
                first_ts = ts
            if last_ts is None or ts > last_ts:
                last_ts = ts
        typ = ev.get("type")
        msg = ev.get("message") or {}
        content = msg.get("content")
        if typ == "assistant" and isinstance(content, list):
            for b in content:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    tid, nm = b.get("id"), b.get("name", "?")
                    tool_uses[tid] = {"name": nm, "ts": ts}
                    tool_counts[nm] += 1
                    if nm in ("Agent", "Task"):
                        inp = b.get("input") or {}
                        agent_runs.append({"id": tid,
                                           "type": inp.get("subagent_type") or inp.get("description") or "?",
                                           "dur": None})
        elif typ == "user":
            if isinstance(content, str) and content.strip():
                user_prompts.append(content.strip().replace("\n", " ")[:200])
            elif isinstance(content, list):
                for b in content:
                    if not isinstance(b, dict):
                        continue
                    if b.get("type") == "text" and (b.get("text") or "").strip():
                        user_prompts.append(b["text"].strip().replace("\n", " ")[:200])
                    elif b.get("type") == "tool_result":
                        tid = b.get("tool_use_id")
                        u = tool_uses.get(tid)
                        if u and u.get("ts") and ts:
                            d = (ts - u["ts"]).total_seconds()
                            tool_durs[u["name"]] += d
                            for a in agent_runs:
                                if a["id"] == tid:
                                    a["dur"] = d
                        if b.get("is_error"):
                            errors[(u or {}).get("name", "?")] += 1

    dur_min = round((last_ts - first_ts).total_seconds() / 60, 1) if (first_ts and last_ts) else None
    implementer = ""
    r = _run(["git", "config", "user.name"], cwd=logs_repo)
    if r and r.returncode == 0:
        implementer = (r.stdout or "").strip()
    implementer = implementer or os.environ.get("USERNAME") or "unknown"

    now = datetime.now()
    # ---- build the markdown ----
    L = []
    L.append("# Session %s" % session_id[:8])
    L.append("")
    L.append("- when: %s" % now.strftime("%Y-%m-%d %H:%M"))
    L.append("- implementer: %s" % implementer)
    L.append("- project: %s" % (cwd or "?"))
    L.append("- ended by: %s" % reason)
    L.append("- duration: %s min" % (dur_min if dur_min is not None else "?"))
    L.append("- human turns: %d" % len(user_prompts))
    L.append("")
    if note:
        L.append("## Note (manual /gotcha)")
        L.append(note.strip())
        L.append("")
    L.append("## Tool telemetry")
    if tool_counts:
        L.append("| tool | calls | total s |")
        L.append("|---|---|---|")
        for nm in sorted(tool_counts, key=lambda k: -tool_counts[k]):
            L.append("| %s | %d | %.1f |" % (nm, tool_counts[nm], tool_durs.get(nm, 0.0)))
    else:
        L.append("(no tool calls recorded)")
    L.append("")
    L.append("## Subagents")
    if agent_runs:
        for a in agent_runs:
            L.append("- %s — %s s" % (a["type"], ("%.1f" % a["dur"]) if a["dur"] else "?"))
    else:
        L.append("(none)")
    L.append("")
    if errors:
        L.append("## Errors / retries (where it stalled)")
        for nm, c in sorted(errors.items(), key=lambda kv: -kv[1]):
            L.append("- %s: %d error result(s)" % (nm, c))
        L.append("")
    L.append("## Flow (human prompts, in order)")
    for i, p in enumerate(user_prompts, 1):
        L.append("%d. %s" % (i, p))
    L.append("")
    L.append("## Learnings / reflection")
    L.append("_What got stuck, what was slow, what the human corrected, new gotchas — fill from the"
             " above + the orchestrator's end-of-flow note._")
    L.append("")
    md = "\n".join(L)

    # ---- write + push ----
    sub = os.path.join(logs_repo, "logs", now.strftime("%Y"), now.strftime("%m"))
    os.makedirs(sub, exist_ok=True)
    fname = "%s_%s_%s.md" % (now.strftime("%Y-%m-%d_%H%M%S"),
                             "".join(c for c in implementer if c.isalnum()) or "impl",
                             session_id[:8])
    fpath = os.path.join(sub, fname)
    try:
        open(fpath, "w", encoding="utf-8").write(md)
    except Exception:
        return

    rel = os.path.relpath(fpath, logs_repo).replace("\\", "/")
    for attempt in range(2):
        _run(["git", "pull", "--rebase", "--autostash"], cwd=logs_repo)
        _run(["git", "add", rel], cwd=logs_repo)
        _run(["git", "commit", "-m", "session %s (%s)" % (session_id[:8], implementer)], cwd=logs_repo)
        p = _run(["git", "push"], cwd=logs_repo)
        if p and p.returncode == 0:
            break


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)  # never block session end
