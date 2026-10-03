# dsp-claude-core — Claude brain for Amazon DSP payroll/census implementation

This repo is the Claude Code setup (skills + subagents + prod-query runners) that runs the
**end-to-end DSP implementation workflows** on Uzio. It is **separate from the Streamlit tools**:
those live in the **Unified Audit Tool** repo and are never modified from here. Keep this repo lean so
every implementer can clone it and get the same workflows.

## Workflows (skills)
- **`/prior-payroll-flow`** — prior payroll + employee deductions go-live: setup → load → audit →
  EE deductions → deduction audit → readiness mail. Orchestrator + 5 subagents.
- **`/census-migration`** — census sanity → mapping → preflight → push → triage. + 2 subagents.
- **`/onboarding-logs`** — instant read-only views over the prod onboarding DB (used by both).

## Non-negotiable conventions
1. **The hardcoded tools live in the Unified Audit Tool repo, not here.** Read `UNIFIED_REPO_PATH`
   from `config/paths.local.json`. When a skill/agent references `apps/adp/X` (or `utils/X`), run it
   headless as: `sys.path.insert(0, UNIFIED_REPO_PATH); import apps.adp.X` — never copy or modify the
   tool.
2. **NO MCP.** Run every tool as its **Python backend, headless** (pass files as `BytesIO` with a
   `.name`), exactly as it runs on Streamlit today. MCP wrappers drop the Streamlit input-gathering and
   silently assume things — bad past experience. Infer the tool's output; don't call an MCP tool.
3. **Gather inputs, never assume.** Each tool's required files are listed in its skill. Ask the user
   for them (a **folder** link). Tell the user to keep the client's files in ONE folder (Drive or
   local), not free-floating, so every stage can reference them.
4. **Human-in-the-loop.** Every outward / irreversible action stops for the user: the load API, filing
   a report to Drive, any email, any Uzio change. Subagents only read / run tools / reason / prepare
   and return a verdict; the orchestrator relays it and waits for the go-ahead.
5. **Secrets** (prod creds + JWT) live at **`DSP_SECRETS_DIR`** (env var), per-implementer, and are
   **NEVER committed and NEVER printed** (the mint scripts print only expiry).
6. **The flow can start anywhere.** The `payroll-flow-triage` subagent reads the client's folder and
   decides the entry stage (~80-90% start at stage 1, but a client may arrive only for an audit, the
   readiness mail, or "check my onboarding logs").

## Self-learning log (automatic — do not skip)
Every session is logged for the learning loop. A **`SessionEnd` hook** (`.claude/hooks/log_session.py`)
writes this session's **telemetry** (tool calls + durations, subagent runs, errors, duration, the
human-prompt flow — **never raw outputs / PII / tokens**) to a Markdown file and pushes it to the
**dsp-session-logs** repo (`SESSION_LOGS_REPO` in `config/paths.local.json`). It fires on its own —
the implementer does nothing. Capture an in-the-moment learning anytime with **`/gotcha`**. (Phase 2:
a periodic pass mines these logs to improve the skills + memory.)

## Prod access (read-only)
- NeuronOps (schema `cp_phix_prod1`): `.claude/skills/prior-payroll-flow/nq.py` (+ `mint.py` to
  re-mint the JWT).
- Onboarding DB (`prod_onboarding_db`): `.claude/skills/onboarding-logs/oblogs.py`.
All read `DSP_SECRETS_DIR`. Single SELECTs only; never echo the token or password.

## New implementer
See **SETUP.md** — Claude Max, clone this + the Unified Audit Tool repo, install Python + packages,
place your prod creds in `DSP_SECRETS_DIR`, fill `config/paths.local.json`. Then open this repo in
Claude Code and invoke a workflow.
