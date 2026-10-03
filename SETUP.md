# SETUP — onboard a new implementer

Follow once per machine. ~15 minutes.

## 1. Prerequisites
- **Claude Code** signed in with a **Claude Max** account.
- **Python 3.11+** and packages:
  ```
  pip install streamlit pandas openpyxl xlsxwriter pyyaml
  ```
- **Git** with SSH access to the team repos (HTTPS git is blocked by corporate TLS on these
  machines — use SSH).

## 2. Clone both repos (keep them as siblings)
```
git clone git@github.com:shobhit73/dsp-claude-core.git
git clone git@github.com:shobhit73/dsp-session-logs.git   # where your session logs are pushed
git clone <Unified Audit Tool repo SSH url>               # the Streamlit tools (apps/, utils/)
```
For the census workflow you also need a local checkout of the Uzio onboarding-service source.

## 3. config/paths.local.json
Copy the example and fill in YOUR paths:
```
cp config/paths.example.json config/paths.local.json
```
- `UNIFIED_REPO_PATH` — your Unified Audit Tool checkout (where `apps/adp/...` lives).
- `DSP_SECRETS_DIR` — a PRIVATE folder for your prod creds (NOT inside any git repo).
- `SESSION_LOGS_REPO` — your local `dsp-session-logs` checkout (the SessionEnd hook pushes logs here).
- `UZIO_ONBOARDING_SRC` — (census only) your onboarding-service source checkout.
`config/paths.local.json` is gitignored — it never leaves your machine.

## 4. Environment variables (so the prod-query runners find your creds)
Set these for your shell/session (match `paths.local.json`):
- `DSP_SECRETS_DIR` — same as above (used by `nq.py`, `mint.py`, `oblogs.py`).
- optional: `DSP_GEN_MATRIX`, `DSP_LOGS_OUT` (onboarding-logs output; defaults are fine).

## 5. Your prod creds (per-implementer — never commit, never print)
In `DSP_SECRETS_DIR` place these JSON files (get your prod access from the team first):
- `neuronops-creds.json` → `{"prod": {"username": "<you>@uzio.com", "password": "..."}}`
- `neuronops-jwt.json`   → `{"prod": {"token": "", "exp": 0}}`  (mint.py fills it)
- `onboarding-creds.json`→ `{"prod": {"username": "<you>@uzio.com", "password": "...", "fein": "<a DSP fein>"}}`
- `onboarding-jwt.json`  → `{}`
Mint the NeuronOps JWT once: `python .claude/skills/prior-payroll-flow/mint.py` (prints only expiry).

## 6. Use it
Open THIS repo in Claude Code. Start a workflow:
- `/prior-payroll-flow` (or "Moses Solutions ka payroll setup karna hai")
- `/census-migration` (or "<client> ka census push karo")
The flow asks for the client + vendor + a folder, triages where to start, and runs stage-by-stage —
pausing for your approval at every outward step (API run, Drive filing, email).

## Notes
- You do NOT log into ADP/Paycom from Claude — you download the source files yourself (Tampermonkey)
  and point the flow at the folder.
- The Streamlit tools stay in the Unified repo and are run headless; nothing here modifies them.
