import asyncio
import random

from playwright.async_api import Locator, Page


class HumanActions:
    """Human-like interaction helper to reduce deterministic action timing."""

    async def delay(self, lo: float = 1.0, hi: float = 3.0) -> None:
        await asyncio.sleep(random.uniform(lo, hi))

    async def type_text(self, page: Page, selector: str, text: str) -> None:
        await page.click(selector, timeout=10_000)
        await page.evaluate(
            "(sel) => { const el = document.querySelector(sel); if (el) el.value = ''; }",
            selector,
        )
        for i, char in enumerate(text):
            await page.type(selector, char, delay=random.uniform(40, 160))
            if i > 0 and i % max(1, len(text) // 4) == 0 and random.random() < 0.15:
                await asyncio.sleep(random.uniform(0.2, 0.6))

    async def scroll(self, page: Page, total_px: int = 1200) -> None:
        scrolled = 0
        while scrolled < total_px:
            step = random.randint(100, 350)
            await page.evaluate("(dy) => window.scrollBy(0, dy)", step)
            scrolled += step
            await self.delay(0.2, 0.8)

    async def mouse_move(self, page: Page, x: int, y: int) -> None:
        steps = random.randint(12, 28)
        for _ in range(steps):
            await page.mouse.move(
                x + random.randint(-3, 3), y + random.randint(-3, 3), steps=1
            )
            await self.delay(0.01, 0.07)

    async def click_locator(self, page: Page, locator: Locator) -> None:
        box = await locator.bounding_box()
        if box:
            cx = int(box["x"] + box["width"] / 2)
            cy = int(box["y"] + box["height"] / 2)
            await self.mouse_move(page, cx, cy)
        await self.delay(0.08, 0.25)
        await locator.click(timeout=5_000)
        await self.delay(0.12, 0.35)

    async def press_key(self, page: Page, key: str) -> None:
        await self.delay(0.08, 0.25)
        await page.keyboard.press(key, delay=random.randint(35, 140))
        await self.delay(0.08, 0.25)

    async def goto(
        self, page: Page, url: str, wait_until: str = "domcontentloaded"
    ) -> None:
        await page.goto(url, wait_until=wait_until)
        await self.delay(1.2, 3.4)
