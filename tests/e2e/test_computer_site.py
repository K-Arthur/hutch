"""Scoped marketing claim changes, actual responsive screenshots and source-bound browser evidence."""
import hashlib
import json
import os
from pathlib import Path

import pytest
from tests.e2e.test_design_system import browser, site_server, ROOT  # noqa: F401 fixtures


@pytest.mark.parametrize("width,height", [(360, 780), (768, 1024), (1440, 900)])
def test_supervised_computer_marketing_claims_layout_and_network(browser, site_server, width, height):
    page = browser.new_page(viewport={"width": width, "height": height}, reduced_motion="reduce")
    errors, external, bad_responses = [], [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: external.append(request.url) if not request.url.startswith(site_server) else None)
    page.on("response", lambda response: bad_responses.append([response.url, response.status]) if response.status >= 400 else None)
    evidence = os.environ.get("HUTCH_EVIDENCE_DIR")
    try:
        page.goto(site_server)
        page.get_by_text("Explore model, privacy, and computer details", exact=True).click()
        feature = page.get_by_role("heading", name="Supervised computer use").locator("xpath=ancestor::article")
        feature.scroll_into_view_if_needed()
        assert "workspace-only user files" in feature.inner_text()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        if evidence:
            Path(evidence).mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(Path(evidence) / f"site-computer-{width}.png"), animations="disabled")
        page.get_by_text("Read the approval rules and technical boundaries", exact=True).click()
        limitations = page.get_by_text("Computer control needs explicit permission.", exact=True).locator("xpath=ancestor::li")
        limitations.scroll_into_view_if_needed()
        assert "physical phones" in limitations.inner_text().lower()
        if evidence:
            page.screenshot(path=str(Path(evidence) / f"site-computer-limits-{width}.png"), animations="disabled")
            data = {"viewport": [width, height], "console_errors": errors, "external_requests": external,
                    "failed_responses": bad_responses,
                    "index_sha256": hashlib.sha256((ROOT / "website/index.html").read_bytes()).hexdigest(),
                    "horizontal_overflow": page.evaluate("document.documentElement.scrollWidth - innerWidth")}
            (Path(evidence) / f"site-computer-{width}.json").write_text(json.dumps(data, indent=2))
        assert not errors and not external and not bad_responses, (errors, external, bad_responses)
    finally:
        page.close()
