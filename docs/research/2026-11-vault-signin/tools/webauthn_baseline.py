"""Baseline of the shipped passkey flow in real Chromium with a virtual authenticator.

usage: webauthn_baseline.py UPSTREAM_PORT PROXY_PORT OUT_DIR
Pairs a device with a one-use code, signs in with the passkey, then turns user verification off
and shows what the browser and server do. Reports outcomes only, never a token or cookie value.
"""
import asyncio
import json
import sys
import urllib.request

from playwright.async_api import async_playwright

UP, PP, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
PUBLIC = f"https://hutch.test:{PP}"
OWNER = f"http://127.0.0.1:{UP}"


def owner_post(path: str, body: dict) -> dict:
    req = urllib.request.Request(OWNER + path, method="POST", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "X-Hutch-Request": "1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


async def api(page, method, path, body=None):
    return await page.evaluate("""async ([m, p, b]) => {
        const r = await fetch(p, {method: m, credentials: 'same-origin',
            headers: {'Content-Type': 'application/json', 'X-Hutch-Request': '1'},
            body: b === null ? undefined : JSON.stringify(b)});
        let j = null; try { j = await r.json(); } catch (e) {}
        return {status: r.status, json: j};
    }""", [method, path, body])


async def authenticator(context, page, uv: bool):
    cdp = await context.new_cdp_session(page)
    await cdp.send("WebAuthn.enable")
    added = await cdp.send("WebAuthn.addVirtualAuthenticator", {"options": {
        "protocol": "ctap2", "transport": "internal", "hasResidentKey": True,
        "hasUserVerification": True, "isUserVerified": uv, "automaticPresenceSimulation": True}})
    return cdp, added["authenticatorId"]


async def pair(page):
    code = owner_post("/api/v1/pairing/codes", {})["code"]
    await page.goto(PUBLIC + "/pair")
    await page.fill("#code", code)
    await page.click("#pair-submit")
    await page.wait_for_selector("#pair-success:not([hidden])", timeout=15000)
    print("1. pair with virtual authenticator (UV on): success page shown")


async def login(page, label):
    await page.context.clear_cookies()
    await page.goto(PUBLIC + "/login")
    await page.click("#passkey-login")
    try:
        await page.wait_for_url(lambda u: not u.endswith("/login"), timeout=8000)
        outcome = "signed in"
    except Exception:
        err = await page.text_content("#passkey-error")
        outcome = f"refused: {(err or '').strip()[:110]!r}"
    print(f"{label}: {outcome}")


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--host-resolver-rules=MAP hutch.test 127.0.0.1"])
        context = await browser.new_context(ignore_https_errors=True, viewport={"width": 1280, "height": 800})
        page = await context.new_page()
        cdp, auth_id = await authenticator(context, page, uv=True)
        await pair(page)
        s = await api(page, "GET", "/api/v1/session")
        print("2. session after pairing:", s["status"], {k: s["json"].get(k) for k in ("principal", "label", "capabilities")})
        for path in ("/api/v1/vault", "/api/v1/devices"):
            r = await api(page, "GET", path)
            print(f"3. paired principal GET {path}:", r["status"], str(r["json"])[:90])
        await login(page, "4. fresh sign-in with passkey, UV on")
        await cdp.send("WebAuthn.setUserVerified", {"authenticatorId": auth_id, "isUserVerified": False})
        await login(page, "5. fresh sign-in, authenticator cannot verify the user")
        await cdp.send("WebAuthn.setUserVerified", {"authenticatorId": auth_id, "isUserVerified": True})
        await login(page, "6. sign-in again, UV restored")
        creds = await cdp.send("WebAuthn.getCredentials", {"authenticatorId": auth_id})
        print("7. credentials held by the authenticator:", len(creds["credentials"]),
              "| resident:", [c.get("isResidentCredential") for c in creds["credentials"]],
              "| signCount:", [c.get("signCount") for c in creds["credentials"]])
        owner = await browser.new_context(viewport={"width": 1280, "height": 900})
        op = await owner.new_page()
        await op.goto(OWNER + "/connections", wait_until="networkidle")
        await op.click('[data-connection-open="phone"]')
        await op.wait_for_selector("#connection-phone-devices", state="visible", timeout=8000)
        if not await op.evaluate("document.querySelector('#connection-phone-devices').open"):
            await op.click("#connection-phone-devices summary")
        await op.wait_for_timeout(500)
        row = await op.text_content("#connection-phone-devices .device-row")
        print("8. owner dashboard device row text:", " ".join((row or "").split()))
        await op.locator("#connection-phone-devices").screenshot(path=f"{OUT}/paired-devices-row.png")
        await browser.close()

asyncio.run(main())
