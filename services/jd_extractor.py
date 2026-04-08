import asyncio
import json
import random
import re
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from configs import HEADLESS, LINKEDIN_CREDENTIALS, LOGIN_WAIT_SECONDS
from models.opportunity import Opportunity, load_opportunities, save_opportunities

_PROJECT_DATA = Path(__file__).parent.parent / "project_data"

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


def _load_source_doms() -> dict[str, dict]:
    with open(_PROJECT_DATA / "source_doms.json", encoding="utf-8") as f:
        return json.load(f)


def _domain_key(url: str) -> str:
    host = urlparse(url).hostname or ""
    return host.removeprefix("www.")


def _is_missing_description(opp: Opportunity) -> bool:
    return not (opp.job_description and opp.job_description.strip())


def sanitize_utf8(text: str) -> str:
    # Remove control characters except newlines/tabs to keep JSON output clean.
    cleaned = text.replace("\x00", "")
    cleaned = re.sub(r"[\x01-\x08\x0B\x0C\x0E-\x1F\x7F]", "", cleaned)
    cleaned = re.sub(r"\r\n?", "\n", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = cleaned.strip()
    return cleaned.encode("utf-8", "ignore").decode("utf-8", "ignore")


async def _human_delay(lo: float = 0.12, hi: float = 0.55) -> None:
    await asyncio.sleep(random.uniform(lo, hi))


async def _human_mouse_move(page: Page, x: int, y: int) -> None:
    steps = random.randint(12, 28)
    for _ in range(steps):
        await page.mouse.move(x + random.randint(-3, 3), y + random.randint(-3, 3), steps=1)
        await _human_delay(0.01, 0.07)


async def _human_key_action(page: Page, key: str) -> None:
    await _human_delay(0.08, 0.25)
    await page.keyboard.press(key, delay=random.randint(35, 140))
    await _human_delay(0.08, 0.25)


async def _human_click(page: Page, locator) -> None:
    box = await locator.bounding_box()
    if box:
        cx = int(box["x"] + box["width"] / 2)
        cy = int(box["y"] + box["height"] / 2)
        await _human_mouse_move(page, cx, cy)
    await _human_delay(0.08, 0.25)
    await locator.click(timeout=5_000)
    await _human_delay(0.12, 0.35)


async def _launch_stealth_browser(playwright) -> Browser:
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


async def _new_stealth_context(browser: Browser) -> BrowserContext:
    context = await browser.new_context(
        viewport={"width": 1366, "height": 768},
        user_agent=_USER_AGENT,
        locale="en-US",
        extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
    )
    await context.add_init_script(_STEALTH_SCRIPT)
    return context


async def _login_linkedin(page: Page, doms: dict) -> None:
    email = LINKEDIN_CREDENTIALS.get("email", "")
    password = LINKEDIN_CREDENTIALS.get("password", "")
    if not email or not password:
        print("LinkedIn credentials not found. Skipping JD extraction.")
        return

    await page.goto(doms["login_url"], wait_until="domcontentloaded")
    await _human_delay(1.0, 2.4)

    if "linkedin.com/login" not in page.url:
        print("Already authenticated for LinkedIn session.")
        return

    await page.click(doms["login_email_field"], timeout=10_000)
    await _human_delay(0.1, 0.3)
    await page.type(doms["login_email_field"], email, delay=random.uniform(35, 110))
    await _human_delay(0.3, 0.8)

    await page.click(doms["login_password_field"], timeout=10_000)
    await _human_delay(0.1, 0.3)
    await page.type(doms["login_password_field"], password, delay=random.uniform(35, 110))
    await _human_delay(0.2, 0.6)

    await page.click(doms["login_submit"])
    try:
        await page.wait_for_selector(doms["post_login_indicator"], timeout=LOGIN_WAIT_SECONDS * 1_000)
    except Exception:
        print("LinkedIn login indicator did not appear before timeout; continuing cautiously.")


class JDExtractor:
    def __init__(self) -> None:
        self.opportunities = load_opportunities()
        self.all_doms = _load_source_doms()

    def _target_opportunities(self) -> list[Opportunity]:
        return [
            opp
            for opp in self.opportunities
            if opp.source_url
            and _domain_key(opp.source_url) == "linkedin.com"
            and _is_missing_description(opp)
        ]

    async def _expand_more(self, page: Page, doms: dict) -> None:
        expand_selectors = doms.get("jd_expand_more_button")
        if isinstance(expand_selectors, str):
            expand_selectors = [expand_selectors]
        if not expand_selectors:
            expand_selectors = [
                "button[aria-label*='more' i]",
                "button.inline-show-more-text__button",
                "button.show-more-less-html__button",
            ]

        for selector in expand_selectors:
            try:
                locator = page.locator(selector).first
                if await locator.count() == 0:
                    continue
                visible = await locator.is_visible(timeout=1_500)
                if not visible:
                    continue
                text = (await locator.inner_text()).strip().lower()
                aria = (await locator.get_attribute("aria-label") or "").strip().lower()
                if "more" in text or "more" in aria:
                    await _human_click(page, locator)
                    await _human_delay(0.4, 0.9)
                    return
            except Exception:
                continue

        # JS fallback for A/B variants where selector text differs.
        try:
            expanded = await page.evaluate("""() => {
                const nodes = [...document.querySelectorAll('button, a, span[role="button"]')];
                for (const node of nodes) {
                    const txt = (node.innerText || '').trim().toLowerCase();
                    const aria = (node.getAttribute('aria-label') || '').trim().toLowerCase();
                    if (txt.includes('more') || aria.includes('more')) {
                        node.click();
                        return true;
                    }
                }
                return false;
            }""")
            if expanded:
                await _human_delay(0.4, 0.9)
        except Exception:
            pass

    async def _extract_description_from_url(self, page: Page, url: str, doms: dict) -> str:
        selectors = doms.get("jd_description_container")
        if isinstance(selectors, str):
            selectors = [selectors]
        if not selectors:
            raise RuntimeError("Missing jd_description_container selector config for linkedin.com")

        await page.goto(url, wait_until="domcontentloaded")
        await _human_delay(1.0, 2.2)

        # Add small human-like interactions before extracting visible text.
        await _human_mouse_move(page, random.randint(220, 860), random.randint(180, 620))
        await _human_delay(0.1, 0.35)
        await _human_key_action(page, "PageDown")
        await _human_delay(0.2, 0.5)
        await _human_key_action(page, "PageUp")
        await _human_delay(0.2, 0.45)
        await self._expand_more(page, doms)

        for selector in selectors:
            try:
                await page.wait_for_selector(selector, timeout=8_000)
                raw_text = await page.locator(selector).first.inner_text()
                cleaned = sanitize_utf8(raw_text)
                if cleaned:
                    if len(cleaned) < 80:
                        continue
                    return cleaned
            except Exception:
                continue
        raise RuntimeError(f"JD text not captured for {url}. Check selectors and page state.")

    def _verify_persisted_updates(self, targeted_urls: set[str]) -> None:
        latest = load_opportunities()
        by_url = {opp.source_url: opp for opp in latest if opp.source_url}
        missing_after_save = [
            url for url in targeted_urls
            if not by_url.get(url) or not (by_url[url].job_description and by_url[url].job_description.strip())
        ]
        if missing_after_save:
            raise RuntimeError(
                "Persistence verification failed for URLs with missing JD after save: "
                + ", ".join(missing_after_save)
            )

    def _verify_single_persisted_update(self, url: str) -> None:
        latest = load_opportunities()
        for opp in latest:
            if opp.source_url == url and opp.job_description and opp.job_description.strip():
                return
        raise RuntimeError(f"Persistence verification failed for URL: {url}")

    async def process_missing_descriptions(self) -> dict[str, int]:
        targets = self._target_opportunities()
        stats = {
            "total": len(self.opportunities),
            "eligible": len(targets),
            "updated": 0,
            "skipped": 0,
            "failed": 0,
        }

        if not targets:
            print("No LinkedIn opportunities with missing job descriptions were found.")
            return stats

        linkedin_doms = self.all_doms.get("linkedin.com")
        if not linkedin_doms:
            print("No LinkedIn DOM config found in source_doms.json.")
            stats["failed"] = len(targets)
            return stats

        async with async_playwright() as pw:
            browser = await _launch_stealth_browser(pw)
            context = await _new_stealth_context(browser)
            page = await context.new_page()
            try:
                if linkedin_doms.get("requires_login"):
                    await _login_linkedin(page, linkedin_doms)

                for idx, opp in enumerate(targets, start=1):
                    try:
                        description = await self._extract_description_from_url(page, opp.source_url, linkedin_doms)
                        opp.job_description = description
                        saved = save_opportunities(opp)
                        if not saved:
                            raise RuntimeError(f"Failed to persist updated opportunity for {opp.source_url}")
                        self._verify_single_persisted_update(opp.source_url)
                        stats["updated"] += 1
                        print(f"[{idx}/{len(targets)}] Updated and saved JD for {opp.source_url}")
                    except Exception as exc:
                        stats["failed"] += 1
                        raise RuntimeError(f"Extraction failed for {opp.source_url}: {exc}") from exc
                    await _human_delay(0.5, 1.4)
            finally:
                await page.close()
                await context.close()
                await browser.close()

        if stats["updated"] != stats["eligible"]:
            raise RuntimeError(
                f"JD verification failed: updated={stats['updated']} eligible={stats['eligible']}. "
                "Stopping run to fix extraction before continuing."
            )

        if stats["updated"]:
            self._verify_persisted_updates({opp.source_url for opp in targets})

        return stats


async def run_jd_extractor() -> None:
    extractor = JDExtractor()
    stats = await extractor.process_missing_descriptions()
    print(
        "JD extraction summary: "
        f"total={stats['total']}, "
        f"eligible={stats['eligible']}, "
        f"updated={stats['updated']}, "
        f"skipped={stats['skipped']}, "
        f"failed={stats['failed']}"
    )


if __name__ == "__main__":
    asyncio.run(run_jd_extractor())