"""oblogs.py - instant, pre-formatted views over prod onboarding_automation_history.

Read-only. Talks to the onboarding /query endpoint (PHIX-98714) on api.uzio.com.
All times are printed in IST.

  oblogs.py recent [N]                  last N runs, all clients (default 20)
  oblogs.py client <name|fein> [N]      one client: last N runs + latest run per module
  oblogs.py run <id> [--all]            one run: totals + errors grouped by reason
  oblogs.py running                     runs with no end_time (in progress / stuck)
  oblogs.py today                       every run started today (IST)
  oblogs.py since YYYY-MM-DD [YYYY-MM-DD]   runs in an IST date range
  oblogs.py user <name> [N]             runs started by a user (substring of email)
  oblogs.py clients [text]              fein -> name lookup, with run count + last run
  oblogs.py sql "<select ...>"          raw SELECT; prints a table, saves a CSV
"""
import ast
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, OrderedDict
from datetime import datetime, timedelta, timezone

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
csv.field_size_limit(2 ** 31 - 1)

# Per-implementer paths. Set DSP_SECRETS_DIR (see SETUP.md); fallbacks are the author's paths.
SECRETS = os.environ.get("DSP_SECRETS_DIR",
    r"C:/Users/shobhit.sharma/.claude/projects/C--Users-shobhit-sharma-Downloads-Uzio-Code/memory/_secrets")
GATEWAY = "https://api.uzio.com"
CREDS_FILE = SECRETS + "/onboarding-creds.json"
JWT_FILE = SECRETS + "/onboarding-jwt.json"
GEN_MATRIX = os.environ.get("DSP_GEN_MATRIX", r"C:/Users/shobhit.sharma/Downloads/dsp-ops-dashboard/scripts/gen_matrix.py")
OUT_DIR = os.environ.get("DSP_LOGS_OUT", r"C:/Users/shobhit.sharma/Downloads/onboarding-logs")
TABLE = "onboarding_automation_history"
IST = timezone(timedelta(hours=5, minutes=30))

# Real prod rows, but test employers - not in the dashboard's client list.
SANDBOX = {
    "232332223": "AA prod (sandbox)", "927387483": "AA prod 01 (sandbox)",
    "769465445": "A Mobile Company 1 (sandbox)", "990000001": "DSP 101 (sandbox)",
    "232432324": "DSP 102 (sandbox)", "876876982": "DSP Test (sandbox)",
    "991182990": "DSP Trial (sandbox)", "565656565": "Vatica Health Sandbox (sandbox)",
}

SHORT = {
    "EmployeeCensus": "Census", "PaymentMethodSetup": "Payment",
    "FedTaxWithholding": "FedTax", "StateTaxWithholding": "StateTax",
    "EmployeeDeductions": "Deductions", "EmployeeContributions": "Contributions",
    "WorkerCompensation": "WorkersComp", "PriorPayroll": "PriorPayroll",
    "CompanyJobTitle": "JobTitle", "SocCode": "SocCode", "W2DeliveryMethod": "W2Delivery",
}

# Listing columns. error_messages / optional_validations are left out on purpose:
# a single row can carry 3 MB of them, and response_body already has the counts.
LIGHT = "id, vendor, fein, start_time, end_time, created_by, created_date, response_body"


# ---------------------------------------------------------------- transport
def _post(url, body, headers):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:800]
    except urllib.error.URLError as e:
        die("Cannot reach %s (%s). VPN / network down?" % (GATEWAY, e.reason))


def _jwt():
    try:
        e = json.load(open(JWT_FILE)).get("prod", {})
        if e.get("exp", 0) - 60 > time.time():
            return e["token"]
    except Exception:
        pass
    c = json.load(open(CREDS_FILE))["prod"]
    status, body = _post(GATEWAY + "/app/onboarding/token",
                         {"username": c["username"], "password": c["password"],
                          "fein": c["fein"]}, {})
    tok = body.get("token") if isinstance(body, dict) else None
    if status != 200 or not tok:
        die("Onboarding token call failed: %s %s"
            % (status, body.get("error") if isinstance(body, dict) else body))
    try:
        d = json.load(open(JWT_FILE))
    except Exception:
        d = {}
    d["prod"] = {"token": tok, "exp": int(body["expiresAt"] // 1000)}  # ms -> s
    json.dump(d, open(JWT_FILE, "w"), indent=2)
    return tok


def q(sql, size=200):
    """Every page of one SELECT, as a list of row dicts."""
    rows, page = [], 0
    while True:
        status, body = _post(GATEWAY + "/app/onboarding/query",
                             {"sql": sql, "page": page, "size": size},
                             {"AuthorizationHeader": _jwt()})
        if status != 200:
            die("onboarding /query HTTP %s: %s" % (status, body))
        rows.extend(body["data"])
        if not body.get("hasMore"):
            return rows
        page += 1


# ---------------------------------------------------------------- helpers
def die(msg, code=1):
    print(msg)
    sys.exit(code)


_NAMES = None


def names():
    global _NAMES
    if _NAMES is None:
        _NAMES = dict(SANDBOX)
        try:
            src = open(GEN_MATRIX, encoding="utf-8").read()
            m = re.search(r"FEIN_NAME\s*=\s*(\{.*?\})", src, re.S)
            _NAMES.update(ast.literal_eval(m.group(1)))
        except Exception:
            pass
    return _NAMES


NAME_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "names_cache.json")
DASH_SCRIPTS = r"C:/Users/shobhit.sharma/Downloads/dsp-ops-dashboard/scripts"
_OVERVIEW = None


def overview_names():
    """fein -> dsp_name from Supabase client_overview (covers clients newer than
    FEIN_NAME). Cached on disk for a day so the common path stays instant."""
    global _OVERVIEW
    if _OVERVIEW is not None:
        return _OVERVIEW
    try:
        c = json.load(open(NAME_CACHE, encoding="utf-8"))
        if c.get("at", 0) > time.time() - 86400:
            _OVERVIEW = c["names"]
            return _OVERVIEW
    except Exception:
        pass
    _OVERVIEW = {}
    try:
        sys.path.insert(0, DASH_SCRIPTS)
        from supabase_helper import connect
        conn = connect()
        cur = conn.cursor()
        cur.execute("select fein, dsp_name from client_overview where coalesce(fein, '') <> ''")
        _OVERVIEW = {re.sub(r"\D", "", f): n for f, n in cur.fetchall() if n}
        conn.close()
        json.dump({"at": time.time(), "names": _OVERVIEW},
                  open(NAME_CACHE, "w", encoding="utf-8"), indent=1)
    except Exception:
        pass
    return _OVERVIEW


def client_name(fein):
    fein = fein or ""
    return names().get(fein) or overview_names().get(fein) or fein or "?"


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def resolve(arg):
    """Client name / fragment / fein -> fein. Exits with the candidates if ambiguous."""
    a = arg.strip()
    if re.fullmatch(r"\d{2}-?\d{7}", a):
        return a.replace("-", "")
    n = _norm(a)
    pool = dict(overview_names())
    pool.update(names())
    hits = [(f, nm) for f, nm in pool.items() if n and n in _norm(nm)]
    exact = [h for h in hits if _norm(h[1]) == n]
    if len(exact) == 1 or len(hits) == 1:
        return (exact or hits)[0][0]
    if not hits:
        die("No client matches '%s'. Try:  oblogs.py clients <part of name>  (or pass the fein)." % arg, 2)
    print("'%s' matches %d clients - re-run with one of these feins:" % (arg, len(hits)))
    for f, nm in sorted(hits, key=lambda h: h[1]):
        print("  %s  %s" % (f, nm))
    sys.exit(2)


def ts(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00").replace(" ", "T"))
    except ValueError:
        return None


def ist(s, fmt="%d-%b %H:%M"):
    d = ts(s)
    return d.astimezone(IST).strftime(fmt) if d else "-"


def ist_day_start_utc(day):
    d = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=IST)
    return d.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S+00")


def vendor(v):
    v = (v or "").strip().upper()
    return {"PAYCOM": "Paycom", "ADP": "ADP"}.get(v, v or "-")


def jload(raw):
    try:
        return json.loads(raw) if raw else None
    except (ValueError, TypeError):
        return None


def summarize(r):
    resp = jload(r.get("response_body")) or {}
    tmap = resp.get("TotalMap") or {}
    fmap = resp.get("FailureMap") or {}
    smap = resp.get("SuccessMap") or {}
    start, end = ts(r.get("start_time")), ts(r.get("end_time"))
    if end and start:
        secs = int((end - start).total_seconds())
        dur = "%d:%02d" % (secs // 60, secs % 60) if secs < 3600 else "%dh%02d" % (secs // 3600, secs % 3600 // 60)
    else:
        dur = "-"
    failed = sum(int(v or 0) for v in fmap.values())
    if not end:
        age_min = int((datetime.now(timezone.utc) - start).total_seconds() // 60) if start else 0
        if age_min <= 120:
            status = "RUNNING %dm" % age_min
        elif age_min < 48 * 60:
            status = "NO RESULT %dh" % (age_min // 60)
        else:
            status = "NO RESULT %dd" % (age_min // 1440)
    else:
        status = "OK" if failed == 0 else "FAIL %d" % failed
    return {
        "modules": list(tmap.keys()),
        "total": sum(int(v or 0) for v in tmap.values()) if tmap else None,
        "ok": sum(int(v or 0) for v in smap.values()) if smap else None,
        "fail": failed if tmap else None,
        "tmap": tmap, "fmap": fmap, "smap": smap,
        "dur": dur, "status": status,
    }


def table(headers, rows, maxw=48):
    rows = [["-" if c is None else str(c) for c in r] for r in rows]
    rows = [[c if len(c) <= maxw else c[:maxw - 1] + "~" for c in r] for r in rows]
    w = [max([len(h)] + [len(r[i]) for r in rows]) for i, h in enumerate(headers)]
    line = lambda cells: "  ".join(c.ljust(w[i]) for i, c in enumerate(cells)).rstrip()
    print(line(headers))
    print(line(["-" * x for x in w]))
    for r in rows:
        print(line(r))


def run_rows(rows, show_client=True):
    out = []
    for r in rows:
        s = summarize(r)
        mods = ",".join(SHORT.get(m, m) for m in s["modules"]) or "?"
        row = [r["id"], ist(r.get("start_time"))]
        if show_client:
            row.append(client_name(r.get("fein")))
        row += [vendor(r.get("vendor")), mods, s["total"], s["ok"], s["fail"],
                (r.get("created_by") or "").split("@")[0], s["dur"], s["status"]]
        out.append(row)
    heads = ["ID", "Start (IST)"] + (["Client"] if show_client else []) + \
            ["Vendor", "Modules", "Total", "OK", "Fail", "By", "Dur", "Status"]
    table(heads, out, maxw=34)


def save_csv(name, rows):
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, name)
    cols = list(rows[0].keys()) if rows else []
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    return path.replace("/", "\\")


def intarg(v, default):
    try:
        return max(1, min(int(v), 1000))
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------- commands
def cmd_recent(args):
    n = intarg(args[0] if args else None, 20)
    rows = q("select %s from %s order by id desc limit %d" % (LIGHT, TABLE, n))
    print("Last %d onboarding runs (newest first)\n" % len(rows))
    run_rows(rows)


def cmd_client(args):
    if not args:
        die("usage: oblogs.py client <name|fein> [N]")
    n = 15
    if len(args) > 1 and args[-1].isdigit() and not re.fullmatch(r"\d{9}", args[-1]):
        n = intarg(args.pop(), 15)
    fein = resolve(" ".join(args))
    rows = q("select %s from %s where fein = '%s' order by id desc" % (LIGHT, TABLE, fein))
    print("%s  (fein %s)  -  %d runs total, vendor %s\n"
          % (client_name(fein), fein, len(rows),
             vendor(rows[0].get("vendor")) if rows else "-"))
    if not rows:
        return
    print("Latest run per module:")
    latest = OrderedDict()
    for r in rows:  # newest first, so first hit per module wins
        s = summarize(r)
        for m in s["modules"]:
            if m not in latest:
                latest[m] = (r, s)
    table(["Module", "Run", "Start (IST)", "Total", "OK", "Fail", "By"],
          [[SHORT.get(m, m), r["id"], ist(r.get("start_time")), s["tmap"].get(m),
            s["smap"].get(m), s["fmap"].get(m), (r.get("created_by") or "").split("@")[0]]
           for m, (r, s) in sorted(latest.items(), key=lambda kv: SHORT.get(kv[0], kv[0]))])
    print("\nLast %d runs:" % min(n, len(rows)))
    run_rows(rows[:n], show_client=False)


def _issue_rows(blob):
    """{Module: [ {rowNumber, employeeId, errorType, errorDetails}, ... ]} -> flat list."""
    obj = jload(blob)
    out = []
    if isinstance(obj, dict):
        for mod, items in obj.items():
            for it in items or []:
                if isinstance(it, dict):
                    out.append({"module": mod, "row": it.get("rowNumber"),
                                "employeeId": it.get("employeeId"),
                                "type": it.get("errorType"),
                                "details": (it.get("errorDetails") or "").strip()})
                else:
                    out.append({"module": mod, "row": None, "employeeId": None,
                                "type": None, "details": str(it)})
    return out


def _grouped(issues, top=15):
    by_mod = OrderedDict()
    for i in issues:
        by_mod.setdefault(i["module"], []).append(i)
    for mod, items in by_mod.items():
        print("  %s  (%d rows)" % (SHORT.get(mod, mod), len(items)))
        groups = Counter((i["type"], i["details"]) for i in items)
        rows = []
        for (typ, det), c in groups.most_common(top):
            emps = [str(i["employeeId"]) for i in items
                    if (i["type"], i["details"]) == (typ, det) and i["employeeId"]][:3]
            rows.append([c, typ or "-", det, ", ".join(emps) + (" ..." if c > 3 else "")])
        table(["Count", "Type", "Reason", "e.g. employeeId"], rows, maxw=90)
        if len(groups) > top:
            print("  ... %d more distinct reasons (use --all or the CSV)" % (len(groups) - top))
        print()


def cmd_run(args):
    ids = [a for a in args if a.isdigit()]
    if not ids:
        die("usage: oblogs.py run <id> [--all]")
    rid = int(ids[0])
    rows = q("select * from %s where id = %d" % (TABLE, rid))
    if not rows:
        die("No run with id %d." % rid)
    r = rows[0]
    s = summarize(r)
    print("Run %d  |  %s (fein %s)  |  %s  |  by %s"
          % (rid, client_name(r.get("fein")), r.get("fein"), vendor(r.get("vendor")),
             (r.get("created_by") or "").split("@")[0]))
    print("Start %s IST  |  End %s  |  Duration %s  |  %s\n"
          % (ist(r.get("start_time"), "%d-%b-%Y %H:%M:%S"),
             ist(r.get("end_time"), "%H:%M:%S") if r.get("end_time") else "-", s["dur"], s["status"]))
    if not r.get("end_time"):
        print("No end_time and no response yet - the run is still going, or it died without writing a result.\n")
    if s["tmap"]:
        table(["Module", "Total", "OK", "Fail"],
              [[SHORT.get(m, m), s["tmap"].get(m), s["smap"].get(m), s["fmap"].get(m)]
               for m in s["tmap"]])
        print()

    errors = _issue_rows(r.get("error_messages"))
    warns = _issue_rows(r.get("optional_validations"))
    if errors:
        print("ERRORS - %d rows, grouped by reason:" % len(errors))
        _grouped(errors, top=10 ** 6 if "--all" in args else 15)
        if "--all" in args or len(errors) <= 25:
            print("Every error row:")
            table(["Module", "Row", "employeeId", "Type", "Reason"],
                  [[SHORT.get(i["module"], i["module"]), i["row"], i["employeeId"], i["type"], i["details"]]
                   for i in errors], maxw=90)
            print()
        print("Errors CSV: %s" % save_csv("run_%d_errors.csv" % rid, errors))
    else:
        print("No errors recorded for this run.")
    if warns:
        print("\nOPTIONAL VALIDATIONS (warnings) - %d rows:" % len(warns))
        _grouped(warns, top=8)
        print("Warnings CSV: %s" % save_csv("run_%d_warnings.csv" % rid, warns))


def cmd_running(args):
    rows = q("select %s from %s where end_time is null order by id desc" % (LIGHT, TABLE))
    if not rows:
        print("Nothing running - every run has an end_time.")
        return
    print("%d run(s) with no end_time (RUNNING = started <2h ago; NO RESULT = older, never wrote end_time/response)\n" % len(rows))
    run_rows(rows)


def _range(day_from, day_to=None):
    for d in (day_from, day_to):
        if d and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
            die("Dates must be YYYY-MM-DD (IST).")
    where = "created_date >= '%s'" % ist_day_start_utc(day_from)
    if day_to:
        nxt = (datetime.strptime(day_to, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
        where += " and created_date < '%s'" % ist_day_start_utc(nxt)
    rows = q("select %s from %s where %s order by id desc" % (LIGHT, TABLE, where))
    if day_to:
        label = day_from + " to " + day_to
    elif day_from == datetime.now(IST).strftime("%Y-%m-%d"):
        label = "today"
    else:
        label = day_from + " onwards"
    if not rows:
        print("No runs %s (IST)." % label)
        return
    fails = sum(1 for r in rows if (summarize(r)["fail"] or 0) > 0)
    print("%d runs %s (IST) - %d with failures, %d clients\n"
          % (len(rows), label, fails, len({r.get("fein") for r in rows})))
    run_rows(rows)


def cmd_today(args):
    _range(datetime.now(IST).strftime("%Y-%m-%d"))


def cmd_since(args):
    if not args:
        die("usage: oblogs.py since YYYY-MM-DD [YYYY-MM-DD]")
    _range(args[0], args[1] if len(args) > 1 else None)


def cmd_user(args):
    if not args:
        die("usage: oblogs.py user <name> [N]")
    who = args[0]
    if not re.fullmatch(r"[A-Za-z0-9._@-]+", who):
        die("User filter may only contain letters, digits, . _ @ -")
    n = intarg(args[1] if len(args) > 1 else None, 25)
    rows = q("select %s from %s where created_by ilike '%%%s%%' order by id desc limit %d"
             % (LIGHT, TABLE, who, n))
    print("Last %d runs by '%s'\n" % (len(rows), who))
    if rows:
        run_rows(rows)


def cmd_clients(args):
    rows = q("select fein, count(*) as runs, max(created_date) as last_run "
             "from %s group by fein" % TABLE)
    txt = _norm(" ".join(args))
    out = []
    for r in rows:
        nm = client_name(r["fein"])
        if txt and txt not in _norm(nm) and txt not in r["fein"]:
            continue
        out.append([nm, r["fein"], r["runs"], ist(r["last_run"], "%d-%b-%Y %H:%M")])
    out.sort(key=lambda x: x[0].lower())
    print("%d client(s)%s\n" % (len(out), " matching '%s'" % " ".join(args) if args else ""))
    table(["Client", "FEIN", "Runs", "Last run (IST)"], out)


def cmd_sql(args):
    sql = " ".join(args).strip().rstrip(";")
    if not re.match(r"(?is)^\s*(select|with)\b", sql):
        die("Only a single SELECT is allowed.")
    rows = q(sql)
    print("%d rows" % len(rows))
    if not rows:
        return
    cols = list(rows[0].keys())
    table(cols, [[r.get(c) for c in cols] for r in rows[:50]], maxw=40)
    if len(rows) > 50:
        print("... %d more rows in the CSV" % (len(rows) - 50))
    print("\nCSV: %s" % save_csv("sql_%s.csv" % datetime.now().strftime("%Y%m%d_%H%M%S"), rows))


COMMANDS = {
    "recent": cmd_recent, "client": cmd_client, "run": cmd_run, "running": cmd_running,
    "today": cmd_today, "since": cmd_since, "user": cmd_user, "clients": cmd_clients,
    "sql": cmd_sql,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        sys.exit(0 if len(sys.argv) < 2 else 2)
    COMMANDS[sys.argv[1]](sys.argv[2:])
