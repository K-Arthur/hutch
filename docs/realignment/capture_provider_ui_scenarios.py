"""Gate helpers and the catalogue-index scenarios for capture_provider_ui.py.

Every check is recorded with the facts that decided it, including the ones that failed, and the run only
passes when every recorded check passes. Expected values come from the JSON API, never from hand-typed
numbers, so a catalogue change cannot silently turn a check into a fiction.
"""

from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

FOCUS_PROBE = """() => { const e = document.activeElement; if (!e || e === document.body) return null;
  const s = getComputedStyle(e);
  return {tag: e.tagName.toLowerCase(), id: e.id || '', name: e.getAttribute('aria-label') || e.name || (e.textContent || '').trim().slice(0, 40),
          ring: (s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0) || (s.boxShadow && s.boxShadow !== 'none')}; }"""


@dataclass
class Gate:
    origin: str
    out: Path
    viewports: tuple
    axe_path: str
    secrets: list
    state: Path
    checks: list = field(default_factory=list)
    pages: list = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(item["ok"] for item in self.checks) and all(not p["problems"] for p in self.pages)

    def url(self, path: str) -> str:
        return self.origin + path

    def get_json(self, path: str) -> Any:
        with urllib.request.urlopen(self.url(path), timeout=20) as response:
            return json.loads(response.read())

    def check(self, name: str, ok: bool, **facts: Any) -> bool:
        self.checks.append({"check": name, "ok": bool(ok), **facts})
        print(("PASS " if ok else "FAIL ") + name + (" " + json.dumps(facts, default=str)[:200] if not ok else ""), flush=True)
        return bool(ok)

    def page(self, browser, width: int, height: int, **context_args: Any):
        context = browser.new_context(viewport={"width": width, "height": height}, **context_args)
        page = context.new_page()
        page._gate_log = {"console": [], "failed": []}
        page.on("console", lambda m: page._gate_log["console"].append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: page._gate_log["console"].append("pageerror: " + str(e)))
        page.on("requestfailed", lambda r: page._gate_log["failed"].append(r.url))
        page.on("response", lambda r: page._gate_log["failed"].append(f"{r.status} {r.url}")
                if r.status >= 400 and r.url.startswith(self.origin) else None)
        return page

    def visit(self, page, path: str, label: str, ready: str = "main") -> None:
        page.goto(self.url(path), wait_until="networkidle")
        page.wait_for_selector(ready, timeout=15000)

    def measure(self, page, label: str, shot: bool = True) -> dict:
        """Overflow, height, console and request problems, secret scan and a full-page screenshot."""
        page.wait_for_timeout(250)
        facts = page.evaluate("() => ({overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,"
                              " height: document.documentElement.scrollHeight, title: document.title,"
                              " h1: (document.querySelector('h1') || {}).textContent || ''})")
        html = page.content()
        leaked = [s for s in self.secrets if s in html]
        problems = []
        if facts["overflow"] > 0:
            problems.append(f"horizontal overflow {facts['overflow']}px")
        problems += [f"console: {text[:160]}" for text in page._gate_log["console"]]
        problems += [f"request: {text[:160]}" for text in page._gate_log["failed"]]
        if leaked:
            problems.append("a credential value appears in the page")
        if shot:
            page.screenshot(path=str(self.out / f"{label}.png"), full_page=True)
        record = {"page": label, "problems": problems, **facts}
        self.pages.append(record)
        print(("ok   " if not problems else "FAIL ") + label + f" h={facts['height']}" + (" " + "; ".join(problems) if problems else ""), flush=True)
        page._gate_log["console"].clear()
        page._gate_log["failed"].clear()
        return record

    def axe(self, page, label: str) -> None:
        if not self.axe_path:
            self.check(f"axe {label}", True, note="axe-core not run: no --axe path given", ran=False)
            return
        page.add_script_tag(path=self.axe_path)
        result = page.evaluate("async () => { const r = await axe.run(document, {resultTypes: ['violations']});"
                               " return {version: axe.version, violations: r.violations.map(v => ({id: v.id, impact: v.impact,"
                               " count: v.nodes.length, sample: v.nodes.slice(0, 2).map(n => n.target.join(' '))}))}; }")
        bad = [v for v in result["violations"] if v["impact"] in ("serious", "critical")]
        self.check(f"axe {label}: no serious or critical violation", not bad, axe=result["version"],
                   serious=bad, other=[v for v in result["violations"] if v not in bad], ran=True)

    def finish(self) -> None:
        record = {"date": time.strftime("%Y-%m-%d"), "passed": self.passed, "origin": self.origin,
                  "pages": self.pages, "checks": self.checks}
        (self.out / "results.json").write_text(json.dumps(record, indent=2, default=str) + "\n")
        print("PASSED" if self.passed else "FAILED", f"({len(self.checks)} checks, {len(self.pages)} pages)")


def visible_rows(page) -> int:
    return page.locator("[data-provider-card]:not([hidden])").count()


def status_text(page) -> str:
    return page.locator("#provider-filter-status").inner_text().strip()


def expected_for(api: dict, *, text: str = "", status: str = "", auth: str = "", service: str = "") -> int:
    count = 0
    for provider in api["providers"]:
        haystack = " ".join([provider["title"], provider["id"]]).lower()
        if text and text not in haystack:
            continue
        if status and provider["integration_status"] != status:
            continue
        if auth and auth not in {m["type"] for m in provider["auth_methods"]}:
            continue
        if service and service not in provider["services"]:
            continue
        count += 1
    return count


def scenario_index(gate: Gate, browser) -> None:
    api = gate.get_json("/api/v1/providers")
    total = len(api["providers"])
    for label, width, height in gate.viewports:
        page = gate.page(browser, width, height)
        gate.visit(page, "/providers", label, ready="#provider-filters:not([hidden])")
        gate.measure(page, f"providers-{label}")
        page.context.close()
    page = gate.page(browser, 1280, 900)
    gate.visit(page, "/providers", "index", ready="#provider-filters:not([hidden])")
    gate.check("index lists every catalogue provider once", visible_rows(page) == total,
               rows=visible_rows(page), api=total)
    page.fill("#provider-search", "deepseek")
    want = expected_for(api, text="deepseek")
    gate.check("search narrows to the API's matches", visible_rows(page) == want and want >= 1,
               rows=visible_rows(page), want=want, status=status_text(page))
    page.fill("#provider-search", "")
    page.select_option("#filter-status", "implemented")
    want = expected_for(api, status="implemented")
    gate.check("status filter equals the API count", visible_rows(page) == want, rows=visible_rows(page), want=want)
    page.select_option("#filter-status", "")
    page.select_option("#filter-auth", "api_key")
    page.select_option("#filter-service", "video")
    want = expected_for(api, auth="api_key", service="video")
    gate.check("auth and service filters combine with AND", visible_rows(page) == want and want >= 1,
               rows=visible_rows(page), want=want)
    gate.check("filters are written to the URL", "auth=api_key" in page.url and "service=video" in page.url, url=page.url)
    page.reload(wait_until="networkidle")
    gate.check("a reload restores the filters", visible_rows(page) == want
               and page.input_value("#filter-service") == "video", rows=visible_rows(page))
    page.click("#provider-filter-clear")
    gate.check("clear restores every row and the bare URL", visible_rows(page) == total and "?" not in page.url,
               rows=visible_rows(page), url=page.url)
    page.fill("#provider-search", "zzzz-no-such-provider")
    gate.check("no match shows the empty state and says so", page.locator("#provider-no-match").is_visible()
               and "No provider matches" in status_text(page), status=status_text(page))
    page.fill("#provider-search", "")
    page.goto(gate.url("/providers?status=bogus&category=nope"), wait_until="networkidle")
    gate.check("an unknown value in the URL is ignored, not trusted", visible_rows(page) == total, rows=visible_rows(page))
    gate.measure(page, "providers-bogus-query", shot=False)
    page.context.close()


def scenario_keyboard(gate: Gate, browser) -> None:
    page = gate.page(browser, 1280, 900)
    gate.visit(page, "/providers", "keyboard", ready="#provider-filters:not([hidden])")
    page.locator("#catalogue").scroll_into_view_if_needed()
    page.focus("#provider-search")
    order = []
    for _ in range(7):
        probe = page.evaluate(FOCUS_PROBE)
        if probe:
            order.append(probe)
        page.keyboard.press("Tab")
    wanted = ["provider-search", "filter-category", "filter-status", "filter-auth", "filter-service", "provider-filter-clear"]
    gate.check("Tab reaches the filters in reading order, then the first provider link",
               [item["id"] for item in order[:6]] == wanted and order[6]["tag"] == "a", order=order)
    gate.check("every stop in the filter traversal shows a focus ring", all(item["ring"] for item in order), order=order)
    page.fill("#provider-search", "xai")
    page.keyboard.press("Escape")
    gate.check("Escape clears the search and keeps focus there", page.input_value("#provider-search") == ""
               and page.evaluate("document.activeElement.id") == "provider-search")
    page.context.close()


def scenario_axe_and_motion(gate: Gate, browser) -> None:
    # axe is injected as an inline script, which the page's CSP forbids; only this context bypasses it, so
    # every other scenario still runs with the product's CSP enforced.
    page = gate.page(browser, 1280, 900, bypass_csp=True)
    gate.visit(page, "/providers", "axe", ready="#provider-filters:not([hidden])")
    gate.axe(page, "/providers")
    page.context.close()
    page = gate.page(browser, 1280, 900, reduced_motion="reduce")
    gate.visit(page, "/providers", "motion", ready="#provider-filters:not([hidden])")
    running = page.evaluate("document.getAnimations().filter(a => a.playState === 'running').length")
    gate.check("reduced motion: nothing is animating on /providers", running == 0, running=running)
    page.context.close()


SCENARIOS: dict[str, Callable[[Gate, Any], None]] = {
    "index": scenario_index, "keyboard": scenario_keyboard, "axe": scenario_axe_and_motion,
}
