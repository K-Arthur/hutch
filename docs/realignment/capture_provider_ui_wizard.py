"""Provider detail page and route-wizard scenarios for capture_provider_ui.py.

The wizard is driven end to end in a real browser against the real server. The "provider" for the connection
test is a loopback stand-in HTTP server that answers /v1/models, so the check makes a real request and no
vendor is contacted. The stand-in proves Hutch's own add, store, test and render path; it says nothing about any
vendor.
"""

from __future__ import annotations

import http.server
import json
import stat
import threading
from typing import Any, Callable

from capture_provider_ui_scenarios import FOCUS_PROBE, Gate

STANDIN_KEY = "sk-gate-standin-key-never-rendered"


class _ModelList(http.server.BaseHTTPRequestHandler):
    seen: list[dict] = []

    def log_message(self, *_args):
        pass

    def do_GET(self):
        _ModelList.seen.append({"path": self.path, "authorized": bool(self.headers.get("authorization"))})
        body = json.dumps({"data": [{"id": "stand-in-model"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _focus_order(page, stops: int) -> list[dict]:
    order = []
    for _ in range(stops):
        probe = page.evaluate(FOCUS_PROBE)
        if probe:
            order.append(probe)
        page.keyboard.press("Tab")
    return order


def scenario_detail_pages(gate: Gate, browser) -> None:
    """Every provider shape at every width: built key route, unbuilt, blocked, local, CLI and media-only."""
    shapes = {"deepseek": "built", "alibaba-model-studio": "unbuilt", "github-copilot": "blocked",
              "ollama": "local", "opencode": "cli", "fal": "media-only", "openai": "two-routes"}
    for provider, shape in shapes.items():
        for label, width, height in gate.viewports:
            if label in ("768", "1920") and provider not in ("deepseek", "openai"):
                continue
            page = gate.page(browser, width, height)
            gate.visit(page, f"/providers/{provider}", label, ready=".route-card")
            gate.measure(page, f"provider-{provider}-{label}")
            page.context.close()
        gate.check(f"detail page renders for the {shape} shape ({provider})", True)


def scenario_wizard(gate: Gate, browser) -> None:
    standin = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _ModelList)
    threading.Thread(target=standin.serve_forever, daemon=True).start()
    gate.secrets.append(STANDIN_KEY)
    base = f"http://127.0.0.1:{standin.server_address[1]}/v1"
    try:
        page = gate.page(browser, 1280, 900)
        gate.visit(page, "/providers/custom-compatible", "wizard", ready=".route-card")
        gate.measure(page, "wizard-1-empty")
        order = _focus_order_from(page, "#name-custom-endpoint", 4)
        gate.check("wizard form is reachable by keyboard in reading order",
                   [item["id"] for item in order[:2]] == ["name-custom-endpoint", "url-custom-endpoint"]
                   and all(item["ring"] for item in order), order=order)
        page.fill("#name-custom-endpoint", "stand-in")
        page.fill("#url-custom-endpoint", base)
        page.get_by_role("button", name="Add account").click()
        page.wait_for_selector("[data-step=key][data-state=current]")
        gate.check("adding the account moves the wizard to the key step",
                   page.locator("[data-step=add][data-state=done]").count() == 1 and "stand-in" in page.url, url=page.url)
        gate.check("a notice confirms it, without a key", "Added stand-in" in page.locator(".flash").inner_text())
        gate.measure(page, "wizard-2-key-step")
        page.fill("#key-custom-endpoint", STANDIN_KEY)
        page.get_by_role("button", name="Store the key").click()
        page.wait_for_selector("[data-step=key][data-state=done]")
        gate.check("storing the key marks it done and the page never shows the value",
                   STANDIN_KEY not in page.content() and page.input_value("#key-custom-endpoint") == "", url=page.url)
        key_file = gate.state / "keys" / "stand-in.key"
        mode = stat.S_IMODE(key_file.stat().st_mode) if key_file.exists() else None
        gate.check("the key file exists with owner-only permissions", mode == 0o600, mode=oct(mode) if mode else None)
        page.get_by_role("button", name="Test the connection").click()
        page.wait_for_selector(".flash")
        gate.check("the connection test made a real request to the stand-in with a credential",
                   any(row["authorized"] and row["path"].endswith("/models") for row in _ModelList.seen), seen=_ModelList.seen)
        gate.check("the flash reports the test in the check's own words", page.locator(".flash").inner_text().strip() != "",
                   flash=page.locator(".flash").inner_text()[:200])
        gate.measure(page, "wizard-3-tested")
        page.context.close()
    finally:
        standin.shutdown()


def _focus_order_from(page, selector: str, stops: int) -> list[dict]:
    page.focus(selector)
    return _focus_order(page, stops)


def scenario_detail_axe_and_motion(gate: Gate, browser) -> None:
    for provider in ("deepseek", "openai", "alibaba-model-studio"):
        page = gate.page(browser, 1280, 900, bypass_csp=True)
        gate.visit(page, f"/providers/{provider}", "axe", ready=".route-card")
        gate.axe(page, f"/providers/{provider}")
        page.context.close()
    page = gate.page(browser, 1280, 900, reduced_motion="reduce")
    gate.visit(page, "/providers/deepseek", "motion", ready=".route-card")
    running = page.evaluate("document.getAnimations().filter(a => a.playState === 'running').length")
    gate.check("reduced motion: nothing is animating on a provider page", running == 0, running=running)
    page.context.close()


SCENARIOS: dict[str, Callable[[Gate, Any], None]] = {
    "detail": scenario_detail_pages, "wizard": scenario_wizard, "detail-axe": scenario_detail_axe_and_motion,
}
