import random
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

from playwright.async_api import BrowserContext, Page, async_playwright

from configs import (
    JOBS_PER_SOURCE,
    LINKEDIN_CREDENTIALS,
    MAX_PAGES,
    PREFERRED_LOCATIONS,
    SCOPE,
    SKILLS,
    SOURCES,
)
from models.opportunity import Opportunity, save_opportunities
from services.auth import login_linkedin
from services.human_actions import HumanActions
from services.playwright_runtime import PlaywrightRuntime
from services.source_config import domain_key, load_source_doms

_NOISE_PATTERNS = {
    "privacy",
    "terms",
    "business services",
    "cookie",
    "linkedin corporation",
}


def _parse_posted_date(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(timezone.utc)

    cleaned = raw.replace("Posted on", "").strip().split("\n")[0].strip()
    for fmt in ("%B %d, %Y, %I:%M %p", "%B %d, %Y"):
        try:
            return datetime.strptime(cleaned, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


async def _get_all_cards_metadata(page: Page, doms: dict) -> list[dict]:
    return await page.evaluate(
        """([containerSel, cardSel]) => {
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
                .filter(t => t && t !== '\u00b7');
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
    }""",
        [doms["job_results_container"], doms["job_card_item"]],
    )


async def _click_card_by_index(page: Page, doms: dict, idx: int) -> bool:
    return await page.evaluate(
        """([containerSel, cardSel, idx]) => {
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
    }""",
        [doms["job_results_container"], doms["job_card_item"], idx],
    )


def _clean_designation(raw: str | None) -> str | None:
    if not raw:
        return None
    lines = [
        line.strip()
        for line in raw.split("\n")
        if line.strip() and "(Verified job)" not in line
    ]
    return lines[0] if lines else None


def _is_noise_card(designation: str | None, company_name: str | None) -> bool:
    combined = f"{designation or ''} {company_name or ''}".lower()
    return any(pattern in combined for pattern in _NOISE_PATTERNS) or (
        designation is None and company_name is None
    )


async def collect_opportunities_on_page(
    page: Page,
    doms: dict,
    actions: HumanActions,
    collected_so_far: int,
    max_jobs: int,
) -> list[Opportunity]:
    results: list[Opportunity] = []

    try:
        await page.wait_for_selector(doms["job_results_container"], timeout=15_000)
    except Exception:
        print("  [warn] Results container not found on this page.")
        return results

    await actions.scroll(page, total_px=random.randint(800, 1400))
    await actions.delay(1.0, 2.0)

    all_cards = await _get_all_cards_metadata(page, doms)
    remaining = max_jobs - collected_so_far
    to_process = min(len(all_cards), remaining)
    print(f"  Found {len(all_cards)} unique cards on page (processing {to_process}).")

    for idx in range(to_process):
        try:
            card = all_cards[idx]
            texts = card["texts"]
            date_text = card["dateText"]

            designation = _clean_designation(texts[0] if texts else None)
            company_name = texts[1] if len(texts) > 1 else None
            location = texts[2] if len(texts) > 2 else None

            if _is_noise_card(designation, company_name):
                continue

            date_posted = _parse_posted_date(date_text)

            clicked = await _click_card_by_index(page, doms, idx)
            if not clicked:
                print(f"  [warn] Could not click card {idx}")
                continue
            await actions.delay(0.6, 1.2)

            query_params = parse_qs(urlparse(page.url).query)
            job_ids = query_params.get("currentJobId", [])
            source_url = (
                f"https://www.linkedin.com/jobs/view/{job_ids[0]}/"
                if job_ids
                else page.url
            )

            opportunity = Opportunity(
                designation=designation,
                company_name=company_name,
                location=location,
                source_url=source_url,
                date_posted=date_posted,
            )
            results.append(opportunity)
            print(f"    [{idx + 1}] {designation} @ {company_name} - {source_url}")

        except Exception as exc:
            print(f"  [warn] Card {idx}: {exc}")

        await actions.delay(0.3, 0.7)

    return results


def build_query() -> str:
    scope_part = " OR ".join(SCOPE)
    skills_part = " OR ".join(SKILLS)
    locations_part = " OR ".join(PREFERRED_LOCATIONS)
    return f"({scope_part}) AND ({skills_part}) AND ({locations_part})"


class Observer:
    def __init__(self) -> None:
        self.query = build_query()
        self.jobs_per_source = JOBS_PER_SOURCE
        self.max_pages = MAX_PAGES
        self.actions = HumanActions()
        self.runtime = PlaywrightRuntime()

    async def _observe_source(
        self,
        context: BrowserContext,
        source: str,
        all_doms: dict,
    ) -> list[Opportunity]:
        key = domain_key(source)
        doms = all_doms.get(key)
        if not doms:
            print(f"No DOM config found for '{key}' - skipping {source}")
            return []

        if doms.get("requires_login") and not (
            LINKEDIN_CREDENTIALS.get("email") and LINKEDIN_CREDENTIALS.get("password")
        ):
            print(
                f"Skipping {source}: login required but credentials not set in inputs.json."
            )
            return []

        page = await context.new_page()
        opportunities: list[Opportunity] = []

        try:
            if doms.get("requires_login"):
                await login_linkedin(page, doms, LINKEDIN_CREDENTIALS, self.actions)

            print(f"Navigating to {source} ...")
            await self.actions.goto(page, source, wait_until="domcontentloaded")

            print(f"Typing query: {self.query[:80]}...")
            await self.actions.type_text(page, doms["search_keyword_input"], self.query)
            await self.actions.delay(0.5, 1.2)
            await page.keyboard.press("Enter")
            await self.actions.delay(2.5, 5.0)

            page_num = 1
            while (
                len(opportunities) < self.jobs_per_source and page_num <= self.max_pages
            ):
                print(
                    f"  Page {page_num}: collecting cards (have {len(opportunities)} so far)..."
                )
                batch = await collect_opportunities_on_page(
                    page,
                    doms,
                    self.actions,
                    len(opportunities),
                    self.jobs_per_source,
                )
                opportunities.extend(batch)
                print(f"  Page {page_num}: collected {len(batch)} cards.")

                if (
                    len(opportunities) >= self.jobs_per_source
                    or page_num >= self.max_pages
                ):
                    break

                has_next = await page.evaluate(
                    """(sel) => {
                    const btn = document.querySelector(sel);
                    if (!btn) return false;
                    btn.click();
                    return true;
                }""",
                    doms["pagination_next_button"],
                )
                if not has_next:
                    print("  No more pages.")
                    break

                await self.actions.delay(2.5, 5.0)
                page_num += 1

        except Exception as exc:
            print(f"  [error] Observing {source}: {exc}")
        finally:
            await page.close()

        return opportunities

    async def observe(self) -> None:
        all_doms = load_source_doms()
        all_opportunities: list[Opportunity] = []

        async with async_playwright() as playwright:
            browser = await self.runtime.launch_browser(playwright)
            context = await self.runtime.new_context(browser)

            for source in SOURCES:
                print(f"\n--- Observing source: {source} ---")
                results = await self._observe_source(context, source, all_doms)

                if not results:
                    raise RuntimeError(
                        f"No opportunities collected from {source} - check if the page structure has changed and update the DOM config accordingly."
                    )

                all_opportunities.extend(results)
                print(f"--- Collected {len(results)} from {source} ---")

            await context.close()
            await browser.close()

        if all_opportunities:
            saved = save_opportunities(all_opportunities)
            print(f"\nSaved {len(all_opportunities)} opportunities: {saved}")
        else:
            print("\nNo opportunities collected.")
