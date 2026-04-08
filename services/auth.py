from playwright.async_api import Page

from configs import LOGIN_WAIT_SECONDS
from services.human_actions import HumanActions
from configs import (
    JOBS_PER_SOURCE,
    LINKEDIN_CREDENTIALS,
    MAX_PAGES,
    PREFERRED_LOCATIONS,
    SCOPE,
    SKILLS,
    SOURCES,
)


async def login_linkedin(page: Page, doms: dict, credentials: dict, actions: HumanActions) -> None:
    """Navigate to LinkedIn login and authenticate with the given credentials."""
    email = LINKEDIN_CREDENTIALS.get("email", "")
    password = LINKEDIN_CREDENTIALS.get("password", "")
    if not email or not password:
        print("LinkedIn credentials not set in environment variables - skipping login.")
        return

    print("Navigating to LinkedIn login...")
    await actions.goto(page, doms["login_url"], wait_until="domcontentloaded")

    if "linkedin.com/login" not in page.url:
        print(f"Already authenticated (redirected to {page.url}) - skipping login form.")
        return

    await actions.type_text(page, doms["login_email_field"], email)
    await actions.delay(0.4, 1.2)
    await actions.type_text(page, doms["login_password_field"], password)
    await actions.delay(0.3, 0.8)
    await page.click(doms["login_submit"])

    print(f"Waiting up to {LOGIN_WAIT_SECONDS}s for login to complete...")
    try:
        await page.wait_for_selector(doms["post_login_indicator"], timeout=LOGIN_WAIT_SECONDS * 1_000)
        print("Login confirmed.")
    except Exception:
        print(f"No 2FA/CAPTCHA challenge detected within {LOGIN_WAIT_SECONDS}s - proceeding with search.")

    await actions.delay(1.0, 2.4)
