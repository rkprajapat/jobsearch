import asyncio
import re
from urllib.parse import urlparse

from playwright.async_api import Page, async_playwright

from configs import LINKEDIN_CREDENTIALS
from models.opportunity import Opportunity, load_opportunities, save_opportunities
from services.auth import login_linkedin
from services.human_actions import HumanActions
from services.playwright_runtime import PlaywrightRuntime
from services.source_config import domain_key, load_source_doms


def _is_missing_description(opportunity: Opportunity) -> bool:
    return not (opportunity.job_description and opportunity.job_description.strip())


def sanitize_utf8(text: str) -> str:
    cleaned = text.replace("\x00", "")
    cleaned = re.sub(r"[\x01-\x08\x0B\x0C\x0E-\x1F\x7F]", "", cleaned)
    cleaned = re.sub(r"\r\n?", "\n", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = cleaned.strip()
    return cleaned.encode("utf-8", "ignore").decode("utf-8", "ignore")


class JDExtractor:
    def __init__(self) -> None:
        self.opportunities = load_opportunities()
        self.all_doms = load_source_doms()
        self.actions = HumanActions()
        self.runtime = PlaywrightRuntime()

    def _target_opportunities(self) -> list[Opportunity]:
        return [
            opportunity
            for opportunity in self.opportunities
            if opportunity.source_url
            and domain_key(opportunity.source_url) == "linkedin.com"
            and _is_missing_description(opportunity)
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
                if not await locator.is_visible(timeout=1_500):
                    continue

                text = (await locator.inner_text()).strip().lower()
                aria = (await locator.get_attribute("aria-label") or "").strip().lower()
                if "more" in text or "more" in aria:
                    await self.actions.click_locator(page, locator)
                    await self.actions.delay(0.4, 0.9)
                    return
            except Exception:
                continue

        try:
            expanded = await page.evaluate(
                """() => {
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
            }"""
            )
            if expanded:
                await self.actions.delay(0.4, 0.9)
        except Exception:
            pass

    async def _extract_description_from_url(self, page: Page, url: str, doms: dict) -> str:
        selectors = doms.get("jd_description_container")
        if isinstance(selectors, str):
            selectors = [selectors]
        if not selectors:
            raise RuntimeError("Missing jd_description_container selector config for linkedin.com")

        await self.actions.goto(page, url, wait_until="domcontentloaded")

        await self.actions.mouse_move(page, 220, 180)
        await self.actions.delay(0.1, 0.35)
        await self.actions.press_key(page, "PageDown")
        await self.actions.delay(0.2, 0.5)
        await self.actions.press_key(page, "PageUp")
        await self.actions.delay(0.2, 0.45)
        await self._expand_more(page, doms)

        for selector in selectors:
            try:
                await page.wait_for_selector(selector, timeout=8_000)
                raw_text = await page.locator(selector).first.inner_text()
                cleaned = sanitize_utf8(raw_text)
                if cleaned and len(cleaned) >= 80:
                    return cleaned
            except Exception:
                continue

        raise RuntimeError(f"JD text not captured for {url}. Check selectors and page state.")

    def _verify_single_persisted_update(self, url: str) -> None:
        latest = load_opportunities()
        for opportunity in latest:
            if opportunity.source_url == url and opportunity.job_description and opportunity.job_description.strip():
                return
        raise RuntimeError(f"Persistence verification failed for URL: {url}")

    def _verify_persisted_updates(self, targeted_urls: set[str]) -> None:
        latest = load_opportunities()
        by_url = {opp.source_url: opp for opp in latest if opp.source_url}
        missing_after_save = [
            url
            for url in targeted_urls
            if not by_url.get(url) or not (by_url[url].job_description and by_url[url].job_description.strip())
        ]
        if missing_after_save:
            raise RuntimeError(
                "Persistence verification failed for URLs with missing JD after save: "
                + ", ".join(missing_after_save)
            )

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

        async with async_playwright() as playwright:
            browser = await self.runtime.launch_browser(playwright)
            context = await self.runtime.new_context(browser)
            page = await context.new_page()
            try:
                if linkedin_doms.get("requires_login"):
                    await login_linkedin(page, linkedin_doms, LINKEDIN_CREDENTIALS, self.actions)

                for idx, opportunity in enumerate(targets, start=1):
                    try:
                        description = await self._extract_description_from_url(
                            page,
                            opportunity.source_url,
                            linkedin_doms,
                        )
                        opportunity.job_description = description
                        saved = save_opportunities(opportunity)
                        if not saved:
                            raise RuntimeError(
                                f"Failed to persist updated opportunity for {opportunity.source_url}"
                            )
                        self._verify_single_persisted_update(opportunity.source_url)
                        stats["updated"] += 1
                        print(f"[{idx}/{len(targets)}] Updated and saved JD for {opportunity.source_url}")
                    except Exception as exc:
                        stats["failed"] += 1
                        raise RuntimeError(
                            f"Extraction failed for {opportunity.source_url}: {exc}"
                        ) from exc
                    await self.actions.delay(0.5, 1.4)
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
            self._verify_persisted_updates({opportunity.source_url for opportunity in targets})

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
