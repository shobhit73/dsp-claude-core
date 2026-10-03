"""Prod-query runner: reads cached JWT, POSTs a single SELECT to the NeuronOps /query endpoint.
Usage: python pq.py <sqlfile> [page] [size]  -> prints JSON response to stdout."""
import json, sys, time, os, urllib.request

# Per-implementer secrets dir. Set DSP_SECRETS_DIR (see SETUP.md); fallback is the author's path.
SECRETS = os.environ.get("DSP_SECRETS_DIR",
    "C:/Users/shobhit.sharma/.claude/projects/c--Users-shobhit-sharma-Downloads-Uzio-Code/memory/_secrets")
GATEWAY = "https://api.uzio.com"

jwt = json.load(open(SECRETS + "/neuronops-jwt.json"))["prod"]
if jwt["exp"] - 60 < time.time():
    print(json.dumps({"error": "JWT expired — re-mint"})); raise SystemExit(1)

sql = open(sys.argv[1], encoding="utf-8").read().strip()
page = int(sys.argv[2]) if len(sys.argv) > 2 else 0
size = int(sys.argv[3]) if len(sys.argv) > 3 else 500

body = json.dumps({"sql": sql, "page": page, "size": size}).encode()
req = urllib.request.Request(GATEWAY + "/api/neuronops/query", data=body, method="POST",
    headers={"Content-Type": "application/json",
             "Authorization": "Bearer " + jwt["token"],
             "X-Auth-Type": "bearer"})
try:
    with urllib.request.urlopen(req, timeout=120) as r:
        print(r.read().decode())
except urllib.error.HTTPError as e:
    print(json.dumps({"http_error": e.code, "body": e.read().decode()[:500]})); raise SystemExit(1)
