"""Re-mint the NeuronOps prod JWT from stored creds. Prints only success + expiry.
Never prints the token or password."""
import json, base64, time, os, urllib.request, urllib.error

# Per-implementer secrets dir. Set DSP_SECRETS_DIR (see SETUP.md); fallback is the author's path.
SECRETS = os.environ.get("DSP_SECRETS_DIR",
    "C:/Users/shobhit.sharma/.claude/projects/c--Users-shobhit-sharma-Downloads-Uzio-Code/memory/_secrets")
GATEWAY = "https://api.uzio.com"
creds = json.load(open(SECRETS + "/neuronops-creds.json", encoding="utf-8"))["prod"]

body = json.dumps({"username": creds["username"], "password": creds["password"]}).encode()
req = urllib.request.Request(GATEWAY + "/api/auth/token", data=body, method="POST",
                            headers={"Content-Type": "application/json"})  # NO X-Auth-Type on token endpoint
try:
    with urllib.request.urlopen(req, timeout=60) as r:
        resp = json.loads(r.read().decode())
except urllib.error.HTTPError as e:
    print("MINT FAILED: HTTP", e.code, e.read().decode()[:300]); raise SystemExit(1)

token = resp.get("token") or resp.get("access_token") or resp.get("accessToken") or resp.get("jwt")
if not token:
    print("MINT FAILED: no token field in response. keys:", list(resp.keys())); raise SystemExit(1)

payload = token.split(".")[1]
payload += "=" * ((4 - len(payload) % 4) % 4)
exp = json.loads(base64.urlsafe_b64decode(payload))["exp"]

jwt_path = SECRETS + "/neuronops-jwt.json"
d = json.load(open(jwt_path, encoding="utf-8"))
d["prod"] = {"token": token, "exp": exp}
json.dump(d, open(jwt_path, "w", encoding="utf-8"))
print("MINTED OK. valid for", int(exp - time.time()), "sec (~", round((exp-time.time())/60), "min).")
