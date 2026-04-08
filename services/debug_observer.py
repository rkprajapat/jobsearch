"""
Diagnostic script: logs in to LinkedIn, captures screenshots and HTML snippets
at each key step so we can verify/fix selectors in source_doms.json.

Run from project root (with venv active):
    python -m services.debug_observer
"""

import asyncio
import re
import sys
import urllib.parse
from pathlib import Path

from playwright.async_api import async_playwright

from configs import LINKEDIN_CREDENTIALS, LOGIN_WAIT_SECONDS
from services.human_actions import HumanActions
from services.playwright_runtime import PlaywrightRuntime

_PROJECT_DATA = Path(__file__).parent.parent / "project_data"
_ACTIONS = HumanActions()
_RUNTIME = PlaywrightRuntime()

SCREENSHOTS = _PROJECT_DATA / "debug_screenshots"
SCREENSHOTS.mkdir(parents=True, exist_ok=True)


async def save_screenshot(page, name: str) -> None:
    path = SCREENSHOTS / f"{name}.png"
    await page.screenshot(path=str(path), full_page=False)
    print(f"  [screenshot] {path}")


async def dump_html_around(page, selector: str, label: str) -> None:
    """Print outer HTML of the first matching element (or note if absent)."""
    try:
        el = await page.query_selector(selector)
        if el:
            html = await el.evaluate("e => e.outerHTML")
            print(f"  [html:{label}] {html[:400]}")
        else:
            print(f"  [html:{label}] NOT FOUND: {selector}")
    except Exception as exc:
        print(f"  [html:{label}] ERROR: {exc}")


async def dump_all_inputs(page, label: str) -> None:
    """Dump all visible input elements on the page."""
    inputs = await page.query_selector_all("input:visible")
    print(f"  [inputs:{label}] found {len(inputs)} visible inputs")
    for i, inp in enumerate(inputs[:10]):
        try:
            html = await inp.evaluate("e => e.outerHTML")
            print(f"    [{i}] {html[:300]}")
        except Exception:
            pass


async def main():
    email = LINKEDIN_CREDENTIALS.get("email", "")
    password = LINKEDIN_CREDENTIALS.get("password", "")
    if not email or not password:
        print("Credentials not set in inputs.json. Exiting.")
        sys.exit(1)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=False,
            args=["--start-maximized"],
        )
        context = await _RUNTIME.new_context(browser)
        page = await context.new_page()

        # ── STEP 1: Login ────────────────────────────────────────────────────
        print("\n=== STEP 1: Login ===")
        await page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
        await _ACTIONS.delay(1.5, 2.5)
        await save_screenshot(page, "01_login_page")
        await dump_html_around(page, "#username", "email_field")
        await dump_html_around(page, "#password", "password_field")
        await dump_html_around(page, "button[type='submit']", "submit_button")

        await _ACTIONS.type_text(page, "#username", email)
        await _ACTIONS.delay(0.4, 1.0)
        await _ACTIONS.type_text(page, "#password", password)
        await _ACTIONS.delay(0.3, 0.7)
        await page.click("button[type='submit']")
        await save_screenshot(page, "02_after_submit")

        print(f"Waiting up to {LOGIN_WAIT_SECONDS}s for post-login indicator...")
        try:
            await page.wait_for_selector("div.global-nav__me", timeout=LOGIN_WAIT_SECONDS * 1_000)
            print("  Login confirmed.")
        except Exception:
            print("  Timeout — proceeding.")
        await _ACTIONS.delay(1.5, 2.5)
        await save_screenshot(page, "03_post_login")

        # ── STEP 2: Navigate to jobs page ────────────────────────────────────
        print("\n=== STEP 2: Navigate to /jobs/ ===")
        print(f"  Current URL: {page.url}")
        print(f"  Page title:  {await page.title()}")
        # Capture body text to see if we're on a verify/challenge page
        body_text = await page.evaluate("document.body.innerText")
        print(f"  Body text (first 500): {body_text[:500]}")

        await page.goto("https://www.linkedin.com/jobs/", wait_until="domcontentloaded")
        await _ACTIONS.delay(2.0, 3.5)
        print(f"  Jobs URL: {page.url}")
        print(f"  Jobs title: {await page.title()}")
        await save_screenshot(page, "04_jobs_page")

        # Dump ALL inputs (visible or not) with full HTML
        all_inputs = await page.query_selector_all("input")
        print(f"\n  ALL inputs on jobs page: {len(all_inputs)}")
        for i, inp in enumerate(all_inputs[:15]):
            try:
                html = await inp.evaluate("e => e.outerHTML")
                visible = await inp.is_visible()
                print(f"    [{i}] visible={visible} {html[:600]}")
            except Exception:
                pass

        # Probe known candidate selectors
        candidates = [
            "input[data-view-name='search-global-typeahead-input']",
            "input[aria-label='Search jobs']",
            "input[placeholder='Search jobs']",
            "input[placeholder*='job']",
            "input[placeholder*='Job']",
            "input[type='search']",
            "input.jobs-search-box__text-input",
            "input[id*='jobs-search-box-keyword']",
            "input[role='combobox']",
            "input[aria-label*='Search']",
            "input[aria-label*='search']",
        ]
        print("\n  Probing search input candidates:")
        for sel in candidates:
            el = await page.query_selector(sel)
            if el:
                html = await el.evaluate("e => e.outerHTML")
                print(f"    FOUND — {sel}\n           {html[:400]}")
            else:
                print(f"    miss  — {sel}")

        # ── STEP 3: Try typing in matched input then press Enter ──────────────
        print("\n=== STEP 3: Type query & submit ===")
        query = "head AI"
        typed = False
        for sel in candidates:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                print(f"  Typing into: {sel}")
                await _ACTIONS.type_text(page, sel, query)
                await _ACTIONS.delay(0.5, 1.0)
                await page.keyboard.press("Enter")
                typed = True
                break
        if not typed:
            print("  No visible search input found.")
            encoded = urllib.parse.quote_plus(query)
            search_url = f"https://www.linkedin.com/jobs/search/?keywords={encoded}"
            print(f"  Trying direct search URL: {search_url}")
            await page.goto(search_url, wait_until="domcontentloaded")
        await save_screenshot(page, "05_after_search")
        print(f"  URL after search: {page.url}")
        print(f"  Title after search: {await page.title()}")

        await _ACTIONS.delay(4.0, 6.0)

        # ── STEP 4: Find job IDs — search full card HTML + click strategy ─────
        print("\n=== STEP 4: Job ID extraction strategies ===")

        lazy_cols = await page.query_selector_all("div[data-testid='lazy-column']")

        # Strategy A: scan full card HTML for 10-digit numbers
        if lazy_cols:
            id_scan = await lazy_cols[0].evaluate("""col => {
                const cards = [...col.querySelectorAll('div[role="button"][componentkey]')];
                return cards.slice(0, 5).map(card => {
                    const html = card.outerHTML;
                    const matches = html.match(/\\b(\\d{8,12})\\b/g);
                    return {
                        key: card.getAttribute('componentkey'),
                        htmlLen: html.length,
                        numericMatches: matches ? [...new Set(matches)] : []
                    };
                });
            }""")
            print("  Strategy A – numeric IDs in card HTML:")
            for c in id_scan:
                print(f"    key={c['key']} htmlLen={c['htmlLen']} numbers={c['numericMatches']}")

        # Strategy B: click each of first 3 cards, read currentJobId from URL
        print("\n  Strategy B – click card → read URL currentJobId:")
        cards = await lazy_cols[0].query_selector_all("div[role='button'][componentkey]")
        for card in cards[:3]:
            key = await card.get_attribute("componentkey")
            await card.click()
            await asyncio.sleep(0.8)
            url = page.url
            m = re.search(r"currentJobId=(\d+)", url)
            job_id = m.group(1) if m else "none"
            print(f"    key={key}  → currentJobId={job_id}  url={url[:80]}")

        await save_screenshot(page, "06_results")

        # ── STEP 5: Check pagination ─────────────────────────────────────────
        print("\n=== STEP 5: Pagination ===")
        pg_candidates = [
            "button[aria-label='Next']",
            "button[aria-label='View next page']",
            "li[data-test-pagination-page-btn] + li button",
            "span[aria-label='Next']",
        ]
        for sel in pg_candidates:
            el = await page.query_selector(sel)
            print(f"    {'FOUND' if el else 'miss '} — {sel}")

        await save_screenshot(page, "07_final")
        print(f"\nAll screenshots saved to: {SCREENSHOTS}")
        print("Inspect them + the output above, then update source_doms.json.")

        await _ACTIONS.delay(2.0, 3.0)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
