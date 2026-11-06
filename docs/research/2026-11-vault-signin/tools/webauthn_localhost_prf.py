"""Two questions for the Phase 1 decisions, answered in real Chromium with a virtual authenticator.

usage: webauthn_localhost_prf.py OUT_JSON

1. Can WebAuthn work on a loopback origin (audit F-11)? Tries rp.id "localhost" on
   http://localhost:PORT, then an IP-literal origin with both an IP rp.id and rp.id "localhost".
2. Does the PRF extension give a deterministic, per-salt secret with a virtual authenticator, and
   what does it do when user verification is off? (Decision input for passkey-derived vault keys.)

A throwaway static page is served from 127.0.0.1 by this script. No Hutch server, no real
credential, no secret: the PRF outputs are compared and measured, never printed.
"""
import asyncio
import http.server
import json
import sys
import threading

from playwright.async_api import async_playwright

PAGE = b"<!doctype html><title>probe</title><p>probe"

JS = """async ([rpId, uv, salts]) => {
  const b = (n) => crypto.getRandomValues(new Uint8Array(n));
  const out = {};
  const enc = new TextEncoder();
  try {
    const cred = await navigator.credentials.create({publicKey: {
      rp: {id: rpId, name: 'probe'}, user: {id: b(16), name: 'owner', displayName: 'owner'},
      challenge: b(32), pubKeyCredParams: [{type: 'public-key', alg: -7}],
      authenticatorSelection: {residentKey: 'required', userVerification: uv},
      extensions: {prf: {}}}});
    const ext = cred.getClientExtensionResults();
    out.create = 'ok';
    out.prfEnabledAtCreate = !!(ext.prf && ext.prf.enabled);
    const get = async (salt) => {
      const a = await navigator.credentials.get({publicKey: {
        rpId, challenge: b(32), userVerification: uv, allowCredentials: [{type: 'public-key', id: cred.rawId}],
        extensions: {prf: {eval: {first: enc.encode(salt)}}}}});
      const r = a.getClientExtensionResults().prf;
      return r && r.results && r.results.first ? new Uint8Array(r.results.first) : null;
    };
    const x1 = await get(salts[0]), x2 = await get(salts[0]), y = await get(salts[1]);
    const eq = (p, q) => p && q && p.length === q.length && p.every((v, i) => v === q[i]);
    out.prfLength = x1 ? x1.length : null;
    out.sameSaltSameOutput = !!eq(x1, x2);
    out.otherSaltOtherOutput = !!(x1 && y && !eq(x1, y));
  } catch (e) { out.error = e.name + ': ' + String(e.message).slice(0, 120); }
  return out;
}"""


def serve() -> http.server.ThreadingHTTPServer:
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(PAGE)

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


async def run_case(browser, name, origin, rp_id, uv_required, verified, has_prf=True):
    ctx = await browser.new_context()
    page = await ctx.new_page()
    await page.goto(origin + "/")
    cdp = await ctx.new_cdp_session(page)
    await cdp.send("WebAuthn.enable")
    opts = {"protocol": "ctap2", "transport": "internal", "hasResidentKey": True,
            "hasUserVerification": True, "isUserVerified": verified,
            "automaticPresenceSimulation": True, "hasPrf": has_prf}
    try:
        await cdp.send("WebAuthn.addVirtualAuthenticator", {"options": opts})
    except Exception as exc:  # an old Chromium without hasPrf
        return {"case": name, "authenticator_error": str(exc)[:120]}
    res = await page.evaluate(JS, [rp_id, "required" if uv_required else "preferred", ["salt-a", "salt-b"]])
    await ctx.close()
    return {"case": name, "origin": origin.split("//")[1].rsplit(":", 1)[0], "rp_id": rp_id,
            "uv_required": uv_required, "authenticator_verified": verified, "has_prf": has_prf, **res}


async def main(out_path: str) -> None:
    srv = serve()
    port = srv.server_address[1]
    results = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        version = browser.version
        loc, ip = f"http://localhost:{port}", f"http://127.0.0.1:{port}"
        results.append(await run_case(browser, "localhost rp, UV on", loc, "localhost", True, True))
        results.append(await run_case(browser, "localhost rp, UV required, authenticator cannot verify",
                                      loc, "localhost", True, False))
        results.append(await run_case(browser, "localhost rp, PRF unsupported by authenticator",
                                      loc, "localhost", False, True, has_prf=False))
        results.append(await run_case(browser, "IP origin, IP rp id", ip, "127.0.0.1", True, True))
        results.append(await run_case(browser, "IP origin, localhost rp id", ip, "localhost", True, True))
        await browser.close()
    srv.shutdown()
    with open(out_path, "w") as fh:
        json.dump({"chromium": version, "results": results}, fh, indent=2)
    print(json.dumps({"chromium": version, "results": results}, indent=2))


asyncio.run(main(sys.argv[1]))
