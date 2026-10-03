---
name: onboarding-logs
description: "Instant read-only look at prod onboarding DB logs (onboarding_automation_history - the Onboarding App API runs: Census, PriorPayroll, Payment, Tax, Deductions, WorkersComp...). One pre-built command, formatted output, no schema exploration. Trigger: /onboarding-logs, onboarding logs dikhao, onboarding db ke logs, onboarding runs, <client> ka census/prior payroll run, run <id> ki errors, API run kyu fail hua, kaunsa run chal raha hai / stuck hai, aaj ke onboarding runs, onboarding_automation_history."
user-invocable: true
allowed-tools: PowerShell, Read
---

# onboarding-logs - answer in ONE command

**Speed is the whole point of this skill.** Do not explore the schema, do not read other
files, do not write ad-hoc Python, do not plan. Map the ask to one row below, run it,
show the output. The script already resolves client names, converts times to IST,
groups errors and saves CSVs.

Run with the PowerShell tool:

```
& "C:\Users\shobhit.sharma\AppData\Local\Programs\Python\Python311\python.exe" "C:\Users\shobhit.sharma\.claude\skills\onboarding-logs\oblogs.py" <command> <args>
```

| User wants | Command |
|---|---|
| latest runs / "logs dikhao" (no client named) | `recent` (or `recent 50`) |
| everything for a client | `client "<name or fein>"` (add a number for more runs: `client stave 40`) |
| why a run failed / errors of run N | `run <id>` (`run <id> --all` for every error row) |
| client's latest errors ("stave ka census kyu fail hua") | `client "<name>"` -> take the run id for that module from "Latest run per module" -> `run <id>`. Two commands, no more. |
| what is running / stuck | `running` |
| today's runs | `today` |
| runs in a date range | `since 2026-09-01` or `since 2026-09-01 2026-09-05` (IST dates) |
| runs by a person | `user tierra` / `user shobhit` |
| find a client's fein / list all clients | `clients` or `clients express` |
| anything else | `sql "select ... from onboarding_automation_history ..."` |

## Showing the result

- The output is already a formatted table: paste it back in a code block as-is. Don't re-tabulate it.
- Add one or two lines at most: the headline (e.g. "358/360 ok, 2 fail: 1 employee not onboarded, 1 missing address state").
  Reply in the user's language (they usually write Hinglish).
- If a CSV path is printed, mention it in one line.
- Name ambiguous (exit code 2, list of feins printed): show the list and ask which one. Don't guess.

## Only when writing `sql` (fallback)

- Table `onboarding_automation_history` (schema `prod_onboarding_db` is the search_path, so no prefix needed).
  Columns: `id, vendor, fein, start_time, end_time, created_by, created_date, updated_*, deleted,
  error_messages, optional_validations, response_body, input_files_metadata, request_body, request_params`.
- `deleted` is NULL on every row - never filter `deleted = 0/false`. The last four columns are always NULL.
- `vendor` is mixed case: `ADP`, `PAYCOM`, `Paycom` - use `upper(vendor)`.
- Times are UTC in the DB. IST = UTC + 5:30.
- `error_messages` / `optional_validations` = `{"<Module>": [{rowNumber, employeeId, errorType, errorDetails}]}`;
  a single row can be 3 MB, so never `select *` over many rows - select the columns you need.
- `response_body` = `{OnboardingAutomationId, Total, TotalMap{module:n}, SuccessMap, FailureMap, employeeMap}`.
- Modules: EmployeeCensus, PriorPayroll, PaymentMethodSetup, FedTaxWithholding, StateTaxWithholding,
  EmployeeDeductions, EmployeeContributions, WorkerCompensation, SocCode, CompanyJobTitle, W2DeliveryMethod.
- `end_time IS NULL` means still running, or died without a result.
- Client names come from `dsp-ops-dashboard/scripts/gen_matrix.py` FEIN_NAME. 8 feins are sandbox employers (the script labels them).

## Rules

- Read-only. Single SELECT only - the endpoint and the script both refuse anything else.
- Never print, echo or copy the credentials in `memory/_secrets/onboarding-creds.json` / `onboarding-jwt.json`.
- Network error means VPN/network is down: say so and stop. Don't retry in a loop.
