"""
Sdílená základna pro všechny Playwright scrapery.
"""
from playwright.async_api import async_playwright, Page, Browser, BrowserContext
import re
import logging

logger = logging.getLogger(__name__)

BROWSER_ARGS = ["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"]
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

COOKIE_SELECTORS = [
    '[data-testid="CookieConsent-accept"]',
    '[data-test="cookie-bar-accept-all"]',
    '#cookieAgreeBtn',
    'button[id*="accept-all"]',
    'button[class*="cookie"][class*="accept"]',
    '.ws-button--accept-all',
    '[class*="CookieConsent"] button',
]

def parse_price(text: str) -> float | None:
    """Parsuje českou cenu: '32,90 Kč' nebo '32.90' -> 32.9"""
    if not text:
        return None
    text = text.replace("\xa0", "").replace(" ", "")
    # Odstraň měnu
    text = re.sub(r'[Kk][Čč].*', '', text).strip()
    # Najdi číslo s českou desetinnou čárkou nebo tečkou
    m = re.search(r'(\d+)[,.](\d{1,2})$', text)
    if m:
        return float(f"{m.group(1)}.{m.group(2)}")
    m = re.search(r'(\d+)', text)
    if m:
        return float(m.group(1))
    return None

async def dismiss_cookies(page: Page):
    """Zkusí zavřít cookie banner."""
    for sel in COOKIE_SELECTORS:
        try:
            await page.click(sel, timeout=1500)
            logger.debug(f"Cookie banner zavřen: {sel}")
            return
        except Exception:
            continue

async def make_context(playwright) -> tuple[Browser, BrowserContext]:
    browser = await playwright.chromium.launch(
        headless=True,
        args=BROWSER_ARGS,
    )
    context = await browser.new_context(
        locale="cs-CZ",
        user_agent=USER_AGENT,
        viewport={"width": 1280, "height": 800},
        extra_http_headers={"Accept-Language": "cs-CZ,cs;q=0.9"},
    )
    # Skryj Playwright fingerprint
    await context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
    """)
    return browser, context
