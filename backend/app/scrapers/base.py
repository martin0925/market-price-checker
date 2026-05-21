"""
Sdílená základna pro všechny Playwright scrapery.
"""
from playwright.async_api import async_playwright, Page, Browser, BrowserContext
import json
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

async def get_price_from_url(url: str) -> dict | None:
    """
    Generický scraper produktové stránky: JSON-LD → DOM fallback.
    Používá se pro obchody bez vlastní implementace get_price_from_url.
    """
    async with async_playwright() as pw:
        browser, context = await make_context(pw)
        page = await context.new_page()
        result = None
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=25_000)
            await dismiss_cookies(page)

            # 1) JSON-LD (schema.org/Product) — funguje pro většinu moderních e-shopů
            jsonld_str = await page.evaluate("""() => {
                for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
                    try {
                        const d = JSON.parse(s.textContent);
                        const nodes = Array.isArray(d) ? d : [d];
                        const prod = nodes.find(n => n && n['@type'] === 'Product');
                        if (prod) return JSON.stringify(prod);
                    } catch(e) {}
                }
                return null;
            }""")

            if jsonld_str:
                data = json.loads(jsonld_str)
                offers = data.get("offers", {})
                if isinstance(offers, list):
                    offers = min(offers, key=lambda o: float(o.get("price") or 999999))
                price = float(offers.get("price") or 0) or None
                if price:
                    high = float(offers.get("highPrice") or 0)
                    name = data.get("name", "")
                    return {
                        "price": price,
                        "orig_price": high if high and high > price else None,
                        "product_name": name,
                        "url": url,
                    }

            # 2) DOM fallback — obecné selektory ceny
            for price_sel in [
                "[itemprop='price'][content]",
                "[itemprop='price']",
                "[data-test*='price']",
                "[class*='actualPrice']",
                "[class*='current-price']",
                "[class*='price--final']",
                ".price",
            ]:
                try:
                    el = page.locator(price_sel).first
                    if not await el.count():
                        continue
                    text = await el.get_attribute("content") or await el.inner_text(timeout=2_000)
                    price = parse_price(text)
                    if not price:
                        continue
                    name = ""
                    for name_sel in ["h1[itemprop='name']", "[itemprop='name']", "h1"]:
                        try:
                            name = await page.locator(name_sel).first.inner_text(timeout=1_000)
                            break
                        except Exception:
                            continue
                    return {"price": price, "orig_price": None, "product_name": name.strip(), "url": url}
                except Exception:
                    continue

        except Exception as e:
            logger.error(f"get_price_from_url({url[:60]}): {e}")
        finally:
            await browser.close()
    return result


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
