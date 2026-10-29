"""Run 4/5 evidence probe: EUIPO eSearch, TMview, CIPO and a USPTO tmsearch UI attempt (2026-10-29).

Read-only browser probe, no logins, no CAPTCHA solving. Prints rendered text for the raw log;
not part of the product. Run: .venv/bin/python .pipeline/brand/2026-10/probe-registers.py
"""
from playwright.sync_api import sync_playwright

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36"

def dump(pg, label):
    try:
        t = pg.inner_text("body")
    except Exception as e:
        t = "ERR:" + str(e)[:200]
    print("=====", label)
    print("URL:", pg.url)
    print("TITLE:", pg.title())
    print(t[:2200].replace("\n\n", "\n"))
    print("=====END", label)

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(user_agent=UA, locale="en-US", viewport={"width": 1280, "height": 900})

    pg = ctx.new_page()
    try:
        pg.goto("https://tmsearch.uspto.gov/search/search-information", wait_until="domcontentloaded", timeout=45000)
        pg.wait_for_timeout(4000)
        inputs = pg.locator("input:visible")
        n = inputs.count()
        print("USPTO visible inputs:", n)
        filled = False
        for i in range(min(n, 6)):
            el = inputs.nth(i)
            ph = (el.get_attribute("placeholder") or "") + "|" + (el.get_attribute("aria-label") or "")
            if "search" in ph.lower() or "serial" in ph.lower() or "mark" in ph.lower():
                el.fill("99695333")
                el.press("Enter")
                filled = True
                print("USPTO filled input", i, ph[:80])
                break
        if not filled and n:
            inputs.nth(0).fill("99695333")
            inputs.nth(0).press("Enter")
            print("USPTO filled first input (fallback)")
        pg.wait_for_timeout(8000)
        dump(pg, "USPTO tmsearch serial 99695333 (UI)")
    except Exception as e:
        print("USPTO ERROR:", type(e).__name__, str(e)[:300])
    pg.close()

    pg = ctx.new_page()
    try:
        pg.goto("https://euipo.europa.eu/eSearch/#basic/hutch", wait_until="domcontentloaded", timeout=45000)
        pg.wait_for_timeout(7000)
        dump(pg, "EUIPO eSearch basic hutch")
    except Exception as e:
        print("EUIPO ERROR:", type(e).__name__, str(e)[:300])
    pg.close()

    pg = ctx.new_page()
    try:
        pg.goto("https://www.tmdn.org/tmview/#/tmview/results?page=1&pageSize=30&criteria=HUTCH", wait_until="domcontentloaded", timeout=45000)
        pg.wait_for_timeout(9000)
        dump(pg, "TMview results HUTCH")
    except Exception as e:
        print("TMVIEW ERROR:", type(e).__name__, str(e)[:300])
    pg.close()

    pg = ctx.new_page()
    try:
        pg.goto("https://ised-isde.canada.ca/cipo/trademark-search/", wait_until="domcontentloaded", timeout=45000)
        pg.wait_for_timeout(4000)
        try:
            pg.locator("input[type=text], input[type=search], input:visible").first.fill("hutch")
            pg.keyboard.press("Enter")
            pg.wait_for_timeout(7000)
        except Exception as e:
            print("CIPO fill error:", type(e).__name__, str(e)[:150])
        dump(pg, "CIPO search hutch")
    except Exception as e:
        print("CIPO ERROR:", type(e).__name__, str(e)[:300])
    pg.close()
    b.close()
