"""Real server + real second process on one database. Generated values only; nothing printed but outcomes."""
import json, os, secrets, subprocess, sys, time, urllib.request, urllib.error

port, state = sys.argv[1], sys.argv[2]
base = f"http://127.0.0.1:{port}"
H = {"Content-Type": "application/json", "X-Hutch-Request": "1"}

def call(method, path, body=None):
    req = urllib.request.Request(base + path, method=method, headers=H,
                                 data=None if body is None else json.dumps(body).encode())
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"{}"), {k.lower(): v for k, v in r.headers.items()}
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}"), {k.lower(): v for k, v in e.headers.items()}

passphrase = "probe-" + secrets.token_urlsafe(18)
canary = "CANARY-" + secrets.token_hex(12)
call("POST", "/api/v1/vault/create", {"passphrase": passphrase})
sid = call("POST", "/api/v1/vault/secrets", {"scope": "workspace", "category": "api_key", "name": "probe", "value": canary})[1]["id"]
print("server vault unlocked after create:", call("GET", "/api/v1/vault")[1]["unlocked"])

# 1. No credential of any kind on this request: no cookie, no bearer, no Origin.
s, body, hdr = call("POST", f"/api/v1/vault/secrets/{sid}/reveal", {})
print("reveal, no credential:", s, "| value in body:", canary in json.dumps(body),
      "| cache-control:", hdr.get("cache-control"), "| pragma:", hdr.get("pragma"))

# 2. What a supervised worker sees: same database, new process, new Store (worker.py:39).
child = subprocess.run([sys.executable, "-I", "-c", (
    "from hutch.config import get_config; from hutch.store import Store; from hutch.vault import vault_for;"
    "st=vault_for(Store(get_config())).status();"
    "print('worker view: initialized=%s unlocked=%s' % (st.initialized, st.unlocked))")],
    env={**os.environ, "HUTCH_STATE_DIR": state}, capture_output=True, text=True, timeout=60)
print(child.stdout.strip() or child.stderr.strip()[-300:])

# 3. Lock-out: wrong passphrases from an unauthenticated caller, then the owner's right one.
call("POST", "/api/v1/vault/lock", {})
codes = [call("POST", "/api/v1/vault/unlock", {"passphrase": "wrong-" + secrets.token_hex(6)})[0] for _ in range(8)]
print("wrong attempts:", codes)
s, body, hdr = call("POST", "/api/v1/vault/unlock", {"passphrase": passphrase})
print("owner's correct passphrase right after:", s, "| retry-after:", hdr.get("retry-after"), "|", body.get("detail"))
time.sleep(int(hdr.get("retry-after") or 0) + 1)
print("after waiting:", call("POST", "/api/v1/vault/unlock", {"passphrase": passphrase})[0])
