from playwright.async_api import Browser, BrowserContext, Playwright

from configs import HEADLESS


class PlaywrightRuntime:
    """Creates browser and context with standard settings for all automation flows."""

    _USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    async def launch_browser(self, playwright: Playwright) -> Browser:
        return await playwright.chromium.launch(
            headless=HEADLESS,
            args=["--start-maximized"],
        )

    async def new_context(self, browser: Browser) -> BrowserContext:
        return await browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent=self._USER_AGENT,
            locale="en-US",
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
        )
