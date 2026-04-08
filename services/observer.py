import asyncio
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from configs import (
    HEADLESS,
    JOBS_PER_SOURCE,
    LINKEDIN_CREDENTIALS,
    LOGIN_WAIT_SECONDS,
    MAX_PAGES,
    PREFERRED_LOCATIONS,
    SCOPE,
    SKILLS,
    SOURCES,
)
from models.opportunity import Opportunity, save_opportunities

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_PROJECT_DATA = Path(__file__).parent.parent / "project_data"

# ---------------------------------------------------------------------------
# DOM configuration
# ---------------------------------------------------------------------------

def load_source_doms() -> dict[str, dict]:
    """Load CSS-selector configurations from project_data/source_doms.json."""
    doms_path = _PROJECT_DATA / "source_doms.json"
    try:
        with open(doms_path) as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"source_doms.json not found at {doms_path}. Exiting.")
        sys.exit(1)
    except json.JSONDecodeError as exc:
        print(f"source_doms.json is invalid JSON: {exc}. Exiting.")
        sys.exit(1)


def domain_key(url: str) -> str:
    """Return the registrable domain (e.g. 'linkedin.com') from a URL."""
    host = urlparse(url).hostname or ""
    return host.removeprefix("www.")

# ---------------------------------------------------------------------------
# Human-behaviour helpers
# ---------------------------------------------------------------------------

async def human_delay(lo: float = 1.0, hi: float = 3.0) -> None:
    """Sleep for a random duration in [lo, hi] seconds."""
    await asyncio.sleep(random.uniform(lo, hi))


async def human_type(page: Page, selector: str, text: str) -> None:
    """Focus a field and type text one character at a time with random delays."""
    await page.click(selector, timeout=10_000)
    await page.evaluate("(sel) => { const el = document.querySelector(sel); if (el) el.value = ''; }", selector)
    for i, char in enumerate(text):
        await page.type(selector, char, delay=random.uniform(40, 160))
        # occasional mid-word stutter pause (~15% chance after any character)
        if i > 0 and i % max(1, len(text) // 4) == 0 and random.random() < 0.15:
            await asyncio.sleep(random.uniform(0.2, 0.6))


async def human_scroll(page: Page, total_px: int = 1200) -> None:
    """Scroll down in random increments summing to roughly total_px."""
    scrolled = 0
    while scrolled < total_px:
        step = random.randint(100, 350)
        await page.evaluate(f"window.scrollBy(0, {step})")
        scrolled += step
        await human_delay(0.2, 0.8)

# ---------------------------------------------------------------------------
# Browser launch & stealth patching
# ---------------------------------------------------------------------------

_STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
window.chrome = { runtime: {} };
""".strip()

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


async def launch_stealth_browser(playwright) -> Browser:
    """Launch a Chromium browser with anti-detection arguments."""
    return await playwright.chromium.launch(
        headless=HEADLESS,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-infobars",
            "--disable-dev-shm-usage",
            "--disable-extensions",
            "--start-maximized",
        ],
    )


async def new_stealth_context(browser: Browser) -> BrowserContext:
    """Create a browser context that mimics a real user."""
    context = await browser.new_context(
        viewport={"width": 1366, "height": 768},
        user_agent=_USER_AGENT,
        locale="en-US",
        extra_http_headers={
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    await context.add_init_script(_STEALTH_SCRIPT)
    return context

# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

async def login_linkedin(page: Page, doms: dict, credentials: dict) -> None:
    """Navigate to LinkedIn login and authenticate with the given credentials."""
    email = credentials.get("email", "")
    password = credentials.get("password", "")
    if not email or not password:
        print("LinkedIn credentials not set in inputs.json — skipping login.")
        return

    print("Navigating to LinkedIn login...")
    await page.goto(doms["login_url"], wait_until="domcontentloaded")
    await human_delay(1.5, 3.0)

    # If LinkedIn redirected away (already logged in), skip form entirely
    if "linkedin.com/login" not in page.url:
        print(f"Already authenticated (redirected to {page.url}) — skipping login form.")
        return

    await human_type(page, doms["login_email_field"], email)
    await human_delay(0.4, 1.2)
    await human_type(page, doms["login_password_field"], password)
    await human_delay(0.3, 0.8)

    await page.click(doms["login_submit"])

    # Wait up to login_wait_seconds for the post-login nav element.
    # If it appears → login confirmed. If timeout → no 2FA/CAPTCHA challenge detected, proceed.
    print(f"Waiting up to {LOGIN_WAIT_SECONDS}s for login to complete...")
    try:
        await page.wait_for_selector(doms["post_login_indicator"], timeout=LOGIN_WAIT_SECONDS * 1_000)
        print("Login confirmed.")
    except Exception:
        print(f"No 2FA/CAPTCHA challenge detected within {LOGIN_WAIT_SECONDS}s — proceeding with search.")
    await human_delay(1.5, 3.0)

# ---------------------------------------------------------------------------
# Card extraction
# ---------------------------------------------------------------------------

def _parse_posted_date(raw: str | None) -> datetime:
    """Parse LinkedIn 'Posted on <date>' span text; fall back to now (UTC)."""
    if not raw:
        return datetime.now(timezone.utc)
    # Strip prefix and trailing newline / relative text (e.g. "\n14 hours ago")
    cleaned = raw.replace("Posted on", "").strip().split("\n")[0].strip()
    for fmt in ("%B %d, %Y, %I:%M %p", "%B %d, %Y"):
        try:
            return datetime.strptime(cleaned, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


async def _get_all_cards_metadata(page: Page, doms: dict) -> list[dict]:
    """Return metadata (texts + date) for every unique card in one JS round-trip."""
    return await page.evaluate("""([containerSel, cardSel]) => {
        const container = document.querySelector(containerSel);
        if (!container) return [];
        const seen = new Set();
        const results = [];
        for (const c of container.querySelectorAll(cardSel)) {
            const k = c.getAttribute('componentkey');
            if (seen.has(k)) continue;
            seen.add(k);
            const texts = [...c.querySelectorAll('p')]
                .map(p => p.innerText.trim())
                .filter(t => t && t !== '·');
            let dateText = '';
            for (const span of c.querySelectorAll('span')) {
                if (span.innerText.trim().startsWith('Posted on')) {
                    dateText = span.innerText.trim();
                    break;
                }
            }
            results.push({ texts, dateText });
        }
        return results;
    }""", [doms["job_results_container"], doms["job_card_item"]])


async def _click_card_by_index(page: Page, doms: dict, idx: int) -> bool:
    """Click the i-th unique card inside the results container using JS (avoids stale handles)."""
    return await page.evaluate("""([containerSel, cardSel, idx]) => {
        const container = document.querySelector(containerSel);
        if (!container) return false;
        const seen = new Set();
        const unique = [];
        for (const c of container.querySelectorAll(cardSel)) {
            const k = c.getAttribute('componentkey');
            if (!seen.has(k)) { seen.add(k); unique.push(c); }
        }
        if (!unique[idx]) return false;
        unique[idx].click();
        return true;
    }""", [doms["job_results_container"], doms["job_card_item"], idx])


_NOISE_PATTERNS = {"privacy", "terms", "business services", "cookie", "linkedin corporation"}


def _clean_designation(raw: str | None) -> str | None:
    """Strip '(Verified job)' clutter and repeated lines from designation text."""
    if not raw:
        return None
    # LinkedIn sometimes prepends "(Verified job)\nReal Title" — take the last non-empty line
    lines = [l.strip() for l in raw.split("\n") if l.strip() and "(Verified job)" not in l]
    return lines[0] if lines else None


def _is_noise_card(designation: str | None, company_name: str | None) -> bool:
    """Return True for footer/non-job cards (Privacy, Terms, etc.)."""
    combined = f"{designation or ''} {company_name or ''}".lower()
    return any(p in combined for p in _NOISE_PATTERNS) or (designation is None and company_name is None)



# ---------------------------------------------------------------------------
# Per-page collection
# ---------------------------------------------------------------------------

async def collect_opportunities_on_page(
    page: Page,
    doms: dict,
    collected_so_far: int,
    max_jobs: int,
) -> list[Opportunity]:
    """Scroll the results page, click each card by index, and collect opportunities."""
    results: list[Opportunity] = []

    try:
        await page.wait_for_selector(doms["job_results_container"], timeout=15_000)
    except Exception:
        print("  [warn] Results container not found on this page.")
        return results

    await human_scroll(page, total_px=random.randint(800, 1400))
    await human_delay(1.0, 2.0)

    all_cards = await _get_all_cards_metadata(page, doms)
    remaining = max_jobs - collected_so_far
    to_process = min(len(all_cards), remaining)
    print(f"  Found {len(all_cards)} unique cards on page (processing {to_process}).")

    for idx in range(to_process):
        try:
            card = all_cards[idx]
            texts = card["texts"]
            date_text = card["dateText"]

            designation  = _clean_designation(texts[0] if texts else None)
            company_name = texts[1] if len(texts) > 1 else None
            location     = texts[2] if len(texts) > 2 else None

            if _is_noise_card(designation, company_name):
                continue

            date_posted = _parse_posted_date(date_text)

            clicked = await _click_card_by_index(page, doms, idx)
            if not clicked:
                print(f"  [warn] Could not click card {idx}")
                continue
            await asyncio.sleep(random.uniform(0.6, 1.2))

            qs = parse_qs(urlparse(page.url).query)
            job_ids = qs.get("currentJobId", [])
            source_url = f"https://www.linkedin.com/jobs/view/{job_ids[0]}/" if job_ids else page.url

            opp = Opportunity(
                designation=designation,
                company_name=company_name,
                location=location,
                source_url=source_url,
                date_posted=date_posted,
            )
            results.append(opp)
            print(f"    [{idx+1}] {designation} @ {company_name} — {source_url}")

        except Exception as exc:
            print(f"  [warn] Card {idx}: {exc}")

        await human_delay(0.3, 0.7)

    return results

# ---------------------------------------------------------------------------
# Query builder
# ---------------------------------------------------------------------------

def build_query() -> str:
    scope_part = " OR ".join(SCOPE)
    skills_part = " OR ".join(SKILLS)
    locations_part = " OR ".join(PREFERRED_LOCATIONS)
    return f"({scope_part}) AND ({skills_part}) AND ({locations_part})"

# ---------------------------------------------------------------------------
# Observer
# ---------------------------------------------------------------------------

class Observer:
    def __init__(self) -> None:
        self.query = build_query()
        self.jobs_per_source = JOBS_PER_SOURCE
        self.max_pages = MAX_PAGES

    async def _observe_source(
        self,
        context: BrowserContext,
        source: str,
        all_doms: dict,
    ) -> list[Opportunity]:
        key = domain_key(source)
        doms = all_doms.get(key)
        if not doms:
            print(f"No DOM config found for '{key}' — skipping {source}")
            return []

        if doms.get("requires_login") and not (
            LINKEDIN_CREDENTIALS.get("email") and LINKEDIN_CREDENTIALS.get("password")
        ):
            print(f"Skipping {source}: login required but credentials not set in inputs.json.")
            return []

        page = await context.new_page()
        opportunities: list[Opportunity] = []

        try:
            # --- Authenticate if required ---
            if doms.get("requires_login"):
                await login_linkedin(page, doms, LINKEDIN_CREDENTIALS)

            # --- Navigate to source ---
            print(f"Navigating to {source} ...")
            await page.goto(source, wait_until="domcontentloaded")
            await human_delay(2.0, 4.0)

            # --- Type search query ---
            print(f"Typing query: {self.query[:80]}...")
            await human_type(page, doms["search_keyword_input"], self.query)
            await human_delay(0.5, 1.2)
            await page.keyboard.press("Enter")
            await human_delay(2.5, 5.0)

            # --- Paginate and collect ---
            page_num = 1
            while len(opportunities) < self.jobs_per_source and page_num <= self.max_pages:
                print(f"  Page {page_num}: collecting cards (have {len(opportunities)} so far)...")
                batch = await collect_opportunities_on_page(
                    page, doms, len(opportunities), self.jobs_per_source
                )
                opportunities.extend(batch)
                print(f"  Page {page_num}: collected {len(batch)} cards.")

                if len(opportunities) >= self.jobs_per_source or page_num >= self.max_pages:
                    break

                # --- Check for next page (JS click bypasses floating overlays) ---
                has_next = await page.evaluate("""(sel) => {
                    const btn = document.querySelector(sel);
                    if (!btn) return false;
                    btn.click();
                    return true;
                }""", doms["pagination_next_button"])
                if not has_next:
                    print("  No more pages.")
                    break
                await human_delay(2.5, 5.0)
                page_num += 1

        except Exception as exc:
            print(f"  [error] Observing {source}: {exc}")
        finally:
            await page.close()

        return opportunities

    async def observe(self) -> None:
        """Launch the stealth browser, scrape all sources, and persist results."""
        all_doms = load_source_doms()
        all_opportunities: list[Opportunity] = []

        async with async_playwright() as pw:
            browser = await launch_stealth_browser(pw)
            context = await new_stealth_context(browser)

            for source in SOURCES:
                print(f"\n--- Observing source: {source} ---")
                results = await self._observe_source(context, source, all_doms)
                all_opportunities.extend(results)
                print(f"--- Collected {len(results)} from {source} ---")

            await context.close()
            await browser.close()

        if all_opportunities:
            saved = save_opportunities(all_opportunities)
            print(f"\nSaved {len(all_opportunities)} opportunities: {saved}")
        else:
            print("\nNo opportunities collected.")

        
    