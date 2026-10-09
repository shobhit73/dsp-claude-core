---
name: prior-payroll-flow
description: "Orchestrates the end-to-end DSP prior-payroll + deductions go-live for a Uzio migration using specialized subagents, with human-in-the-loop gates. Trigger: /prior-payroll-flow, <client> ka payroll setup krna hai, prior payroll chalani/load krni hai, prior payroll audit, EE/employee deductions chalani hai, readiness mail likhni hai, payroll go-live, Q1/Q2/.. chala diya backend check kar."
user-invocable: true
---

# prior-payroll-flow - orchestrator (subagents + human gates)

Takes a DSP client live on Uzio payroll. **You (the main agent) are the conductor**: you run the
hardcoded tools, spawn a specialized subagent at each stage to do the JUDGMENT, and you GATE every
outward action behind the human. Reply in the user's language (usually Hinglish).

## The one principle that drives everything
**Where a hardcoded tool exists, do NOT reason or burn tokens - run it and move on. Apply
intelligence ONLY at the dynamic decisions the tools cannot make.**
- Hardcoded (just run + light check): **Sanity tool** (dates, take-home/net-pay, =ROUND, aggregate),
  **Setup Helper** (earning/deduction/tax mappings + contributions - ~70-80%), the **Audit tools**.
- Dynamic (where the subagents think): bonus discretionary vs non-disc, earning hourly vs flat,
  auto-sync benefits, real-vs-expected audit mismatches, the implementer, failure diagnosis, peer-org
  precedent. Never re-derive what a tool already outputs.

## How the tools run - NO MCP
Run every tool as its **Python backend, headless, exactly as it runs today** - import the module and
call its function with files as `BytesIO`. The backends (verified ADP + Paycom): **`run_comparison`**
(prior-payroll audit), **`run_audit`** (deduction audit), **`run_setup_helper` / `build_setup_xlsx`**
(ADP setup) / **`build_3tab_setup_xlsx`** (Paycom setup), **`generate_uzio_template` /
`generate_corrected_census_xlsx`** (census), **`run_sanity`** (deduction sanity - the Voluntary
Deduction cleaner, ADP + Paycom). **Never call a `render_*` function** - that launches
Streamlit and stalls.
**Do NOT use the audit-tool-server MCP wrappers** - MCP drops the Streamlit input-gathering and
silently assumes things (bad past experience).
**EXCEPTION - the Sanity tool is Streamlit-UI-ONLY** (no headless backend; the `audit_fast_api` core is
incomplete). Running it headless STALLS. The **human** runs it via `streamlit run
apps/adp/prior_payroll_sanity.py` and gives you the `*_cleaned.csv`; you only VERIFY it. Only the Setup
Helper and the audit tools have real headless backends. Each stage must KNOW and GATHER that
tool's inputs (ask the user, never assume a file is present):
- **Sanity**: ADP Prior Payroll file (+ optional Tax Validation Report). Decisions: aggregation
  strategy (full_quarter / preserve_pay_periods), NET<->TAKE-HOME swap.
- **Setup Helper**: sanitized prior-payroll file(s) (+ optional Voluntary Deduction export; +
  historical/wide file for bonus). Client name. Decisions: earning type, bonus include-in-OT, tax
  state/code. (Tax master is internal - not uploaded.)
- **Prior Payroll Audit**: the **cleaned CSVs** + Uzio Prior Payroll Register + the **4** mapping files.
- **Deduction Sanity** (NEW, Stage 4 cleaner): ONE vendor Voluntary Deduction export. Removes rows only
  (never edits a value): direct-deposit, garnishments, **EWA (TapCheck/Payactiv/ZayZoon)**, reimbursements,
  Report-Totals/blank-ID - all default-ticked; FLAGS API-breakers. Output: no-BOM CSV = the EE-deductions
  load file. Decision: tick/un-tick descriptions (defaults usually right; tick PHN cell-phone-reimb / ADV
  pay-advance manually if present).
- **Deduction Audit**: Uzio deduction file + ADP deduction file + mapping.
Needs Python + `streamlit pandas openpyxl xlsxwriter pyyaml` installed locally (see SETUP).

## Scope
- **OUT (the human does this, not you):** finding out WHO to set up (Rohit / the tracker), ADP-vs-
  Paycom, getting credentials, logging into the vendor portal, running the Tampermonkey script to
  download the Q1-Q4 pay-period files + the employee-deduction file + the tax-validation setup, and
  running the onboarding load API (Postman). **You never log into a vendor portal.**
- **IN (you + the subagents):** everything from the downloaded files onward - sanitize, setup +
  mappings, load-verify, audits, readiness mail.

## Entry - ask first, then triage (the flow can start ANYWHERE)
Before scanning anything, ASK the user: which **client**, **ADP or Paycom**, and a **FOLDER** (a local
path or a locally-synced Drive path) where the files live - don't burn tokens guessing or scanning the
whole disk. Then spawn **`payroll-flow-triage`** with that folder; it scans in its OWN context and
returns the file-state map + the recommended entry stage. **Confirm its recommendation with the user**,
then route to that stage. ~80-90% start at stage 1; but a client may arrive only for an audit, only the
readiness mail, or only "check my onboarding logs" - start wherever the files say.
**Standing rule: tell the user to keep the files in ONE folder (Drive or local), not free-floating,**
so every stage can reference them.

## The flow - spawn one subagent per stage, gate between stages
1. **Prior payroll load + verify** -> spawn **`prior-payroll-runner`**. It runs the Sanity tool,
   checks the clean file, then (after the human runs each quarter's API) verifies from prod and
   diagnoses failures. **GATE:** the human runs the API; you present the verification; don't advance
   on a failure.
2. **Setup + mappings** -> spawn **`dsp-setup-advisor`**. It runs the Setup Helper, then decides the
   dynamic calls (bonus disc/non-disc via OT in the file, hourly/flat via hours in the file, auto-sync
   via the tracker) and surfaces each. **GATE:** human confirms the decisions before the Uzio setup is
   applied. (Setup usually precedes load in calendar time, but either order works - the earnings must
   exist before the load maps to them.)
3. **Prior payroll audit** -> spawn **`payroll-audit-analyst`** (PriorPayroll). It runs the audit on
   the CLEANED CSVs, separates real vs expected mismatches, prepares the standard-named report.
   **GATE:** human reviews mismatches; you file to Drive only after approval.
4. **EE deductions load + verify** -> run the **Deduction Sanity tool** (`apps/{adp,paycom}/deduction_sanity.py`,
   headless `run_sanity()`) on the vendor Voluntary Deduction export: it default-drops direct-deposit /
   garnishments / EWA (TapCheck/Payactiv/ZayZoon) / reimbursements / totals and FLAGS API-breakers -> no-BOM
   CSV (the load file). **TapCheck rule: KEEP `IPY->Earned Wage Access` in the MAPPING, but EXCLUDE TapCheck
   from this LOAD** - TapCheck runs EWA client-side, so it must not be assigned on Uzio profiles; the sanity
   tool drops it by default and never touches the mapping. Review the removed rows + flags with the human
   (tick PHN/ADV manually if present). **GATE:** human runs the EmployeeDeductions API, then spawn
   **`prior-payroll-runner`** again (same verify logic) + spot-check one employee (cents/100).
5. **Deduction audit** -> spawn **`payroll-audit-analyst`** (Deduction). TapCheck/EWA is an EXPECTED
   difference (intentionally EXCLUDED from the Uzio load but present in the ADP source) - don't flag it as a
   real mismatch. **GATE:** human approves the filing.
6. **Readiness email** -> spawn **`readiness-coordinator`**. It confirms the implementer from the
   tracker, checks stages are green, returns the house-style draft. **GATE:** you create the Gmail
   DRAFT from its text; the human sends - never auto-send.

## Human-in-the-loop gates (always)
Every outward / irreversible action stops for the human: the load API runs, filing a report to Drive,
creating/sending any email, any Uzio change. Subagents only read, run tools, reason, and prepare -
they return a verdict; you relay it and wait for the go-ahead.

## Shared tooling (stable paths - work in a fresh chat)
- **Tools**: repo `apps/adp/` (sanity, deduction_sanity, setup helper, total_comparison, deduction_audit); Paycom under
  `apps/paycom/`. Run headless (see [[adp-setup-helper-headless-format]]).
- **Prod queries**: onboarding -> the onboarding-logs skill `oblogs.py`
  (`C:\Users\shobhit.sharma\.claude\skills\onboarding-logs\oblogs.py`). NeuronOps -> `nq.py` + `mint.py`
  in THIS skill folder (`.claude/skills/prior-payroll-flow/`). Creds/JWT under
  `.../Downloads/Uzio Code/memory/_secrets/` - **never print the token/password**.
- **Drive filing**: `Amazon DSP/<Client>-DSP/Audit Files/`; report name
  `<Client>_Uzio_<ADP|Paycom>_<PriorPayroll|Deduction|Census>_Audit_Report_<DD_MM_YYYY_HHMM>.xlsx`
  (Rohit's script matches this). Verify the sync via the Drive connector; Downloads is itself synced,
  so keep the final report only in the Audit Files folder.
- `ein` = UUID, not the numeric FEIN. Code changes -> root `Unified_Audit_Tool` (+ `audit_fast_api`),
  not implementors ([[implementors-reduced-deployment]]).

## Subagents (`.claude/agents/`)
`payroll-flow-triage` (entry - where to start), `prior-payroll-runner`, `dsp-setup-advisor`,
`payroll-audit-analyst`, `readiness-coordinator` - all read-only / prepare-only; they run the Python
tools headless and return a verdict; the gates live here in the orchestrator.

## BTK Rush reference (2026-10-02)
Clean pass: 826/826 prior payroll, audit penny-perfect, 626/626 EE deductions, deduction audit 0
mismatch (114 EWA = TapCheck). Implementer was Mercedes (tracker, not assumed).
**Correction (2026-10-07):** those TapCheck rows should NOT have been loaded - TapCheck is client-side EWA and
the client escalated ("Super Urgent | EWA"). Going forward Stage 4's Deduction Sanity default-drops TapCheck
from the LOAD while the mapping keeps `IPY->Earned Wage Access`. See the `ewa-tapcheck-map-not-load` rule.
