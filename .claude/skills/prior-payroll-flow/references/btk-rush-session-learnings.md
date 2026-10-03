# BTK Rush go-live - session log + learnings (2026-10-02/03)

The worked example behind the `prior-payroll-flow` skill. Concrete numbers + every gotcha we hit,
so the next setup goes faster. (ADP client, Amazon DSP, FEIN 842685784, Uzio org id 2181545880.)

## Final numbers (what a clean pass looks like)
- Prior payroll: **4 runs, 826/826 loaded, 0 failures** (Q1 198, Q2 225, Q3 232, Q4/latest 171).
- Prior payroll audit: **all 33 category totals matched to the penny**, 0 mismatches, stub counts
  match, tax effective rates at standard.
- EE deductions: **626/626 loaded, 0 failures**.
- Deduction audit: **626 Data Match, 0 Data Mismatch** (114 EWA "missing in ADP" = TapCheck, expected).

## Stage learnings

### Setup (earnings / deductions / bonuses)
- **Same Day was set Hourly - it's FLAT.** A flat "Other" earning has no `ADDITIONAL HOURS : <code>`
  column and shows a flat $ on the paystub (no rate/hours). Backend: `amount_multiplier=1.0` = hourly,
  `None` = flat. **You CANNOT toggle Hourly off on an existing "Other" earning in the Uzio UI (silent
  no-op - the audit table showed zero MOD revisions). Fix = DELETE + RECREATE as Hourly=No.** The code
  changes (ERN01 -> ERN02) but the earnings mapping matches by NAME, so no mapping edit needed.
- **Bonus disc/non-disc is per CODE.** Only Manager Bonus was provable (1 employee had bonus + OT in
  one period: actual OT $83.08 = blended rate exactly -> non-disc). The other 5 never overlapped OT in
  any period -> **defaulted non-discretionary** (zero-OT rule). All 6 set Include-in-OT = Yes.
- **Lookback/Realtime were never provisioned** (unlike 104/105 DSP peers who have them as is_default
  LK2/NA2). Created manually, lowercase names, W-2 "Not Required" to match peers. Confirm the backend
  audit table (`ups_company_earning_detail_aud`): only revtype=0 ADD = created, no DELETE = nobody
  deleted them, they just weren't there.

### Prior payroll load
- **Feed the API the sanity-CLEANED CSVs**, not raw xlsx (same files feed the audit).
- **Postman's OnboardingAutomationId is STALE** - it showed a Sep-15 Express Package run (1385) while
  the real BTK run was 1441. Always pull the latest run from the onboarding DB (oblogs.py), confirm by
  fein + endDate + associate count.
- Long runs: `end_time` NULL = running; a background poller gives the final numbers hands-free.

### Prior payroll audit
- **The audit tool reads raw-xlsx `=ROUND()` cells as 0** -> all ADP totals 0 -> everything "Mismatch".
  Feed the cleaned CSVs. This was the single biggest time-sink; it looks like a data disaster but is a
  file-choice bug.
- Report must be named `<Client>_Uzio_ADP_<Type>_Audit_Report_<DD_MM_YYYY_HHMM>.xlsx` for Rohit's
  Google Script; the MCP tool names it differently -> rename. File to `Amazon DSP/<Client>-DSP/Audit
  Files/`. The Downloads folder is Drive-synced, so a report saved there duplicates on Drive - keep
  only the Audit Files copy.

### EE deductions
- Remove before loading: direct-deposit (CK/SV), court-ordered (SUPPORT/GARNISHMENT/TAX LEVY),
  **reimbursements** (REI/cell-phone - NEGATIVE amounts = earnings, not deductions; they load as the
  "Reimbursements" EARNING), blank/total rows. Pay Advance: the one employee was terminated -> skip.
- Deduction amounts in the backend are in **CENTS (/100)**; % deductions use `ee_amount_per_pay_percent`.
- **Earned Wage Access (TapCheck) comes from the TapCheck integration**, not our load - prod had 179
  EWA vs 65 in our file; the deduction audit flags the extra 114 as "missing in ADP" = EXPECTED.

### Readiness
- **Confirm the implementer from Shruti's tracker - do NOT assume.** BTK's was Mercedes; the first
  draft wrongly went to Tierra. (Tierra = garnishments line only.)

## Tooling notes
- Deduction cents, peer-org precedent, prod verification all came from prod queries - NeuronOps
  (`nq.py`/`mint.py`) and onboarding (`oblogs.py`). Never print the token/password.
- Code fixes to the tools go to root `Unified_Audit_Tool` (+ `audit_fast_api`), not implementors.
  Spawned a task to make `total_comparison` evaluate `=ROUND` so raw xlsx works directly.
