# dsp-claude-core

Claude Code "core" for **Amazon DSP implementation on Uzio** — the skills + subagents that drive the
two end-to-end workflows, kept separate from the Streamlit tools (which live in the Unified Audit Tool
repo).

- **`/prior-payroll-flow`** — prior payroll + employee deductions go-live (setup → load → audit → EE
  deductions → deduction audit → readiness mail).
- **`/census-migration`** — census sanity → mapping → preflight → push → triage.
- **`/onboarding-logs`** — read-only prod onboarding-DB views.

Design: hardcoded tools run **headless as Python (no MCP)**; subagents add the judgment the tools
can't; **human approves every outward action**; the flow can **start anywhere** (a triage agent reads
the client's folder and decides where to begin).

➡️ **New here? Read [CLAUDE.md](CLAUDE.md) then [SETUP.md](SETUP.md).**
