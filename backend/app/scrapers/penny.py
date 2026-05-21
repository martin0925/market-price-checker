"""
Penny.cz scraper

Penny nemá zdokumentovaný API. Přístup:
  - Search URL: /search?q=QUERY nebo /hledat?q=QUERY
  - DOM: produkty v [class*='product-item'] nebo [class*='ProductCard']
  - Cena: .price__main nebo [class*='Price'] nebo JSON-LD
  - Přeškrtnutá: .price__before, del, [class*='was-price']
"""
import json
import logging
from playwright.async_api import async_playwright, TimeoutError as PWTimeout
from .base import make_context, dismiss_cookies, parse_price

logger = logging.getLogger(__name__)

BASE = "https://www.penny.cz"


async def search_product(query: str) -> dict | None:
    # Zkus různé search URL formáty
    search_urls = [
        f"{BASE}/hledat/{query.replace(' ', '-')}",
        f"{BASE}/search?q={query.replace(' ', '+')}",
        f"{BASE}/hledat?q={query.replace(' ', '+')}",
    ]

    async with async_playwright() as pw:
        browser, context = await make_context(pw)
        page = await context.new_page()
        result = None
        try:
            # Zkus první URL, pokud selže, zkus další
            loaded = False
            for url in search_urls:
                try:
                    resp = await page.goto(url, wait_until="domcontentloaded", timeout=20_000)
                    if resp and resp.status < 400:
                        loaded = True
                        search_url = url
                        break
                except Exception:
                    continue

            if not loaded:
                logger.warning(f"Penny: nepodařilo se načíst search pro '{query}'")
                return None

            await dismiss_cookies(page)

            await page.wait_for_selector(
                "[class*='product-item'], [class*='ProductCard'], "
                "[class*='ProductTile'], article, .product",
                timeout=12_000
            )

            # Zkus JSON-LD
            jsonld = await page.evaluate("""() => {
                for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
                    try {
                        const d = JSON.parse(s.textContent);
                        const arr = Array.isArray(d) ? d : [d];
                        const p = arr.find(x => x['@type'] === 'Product');
                        if (p) return JSON.stringify(p);
                    } catch(e) {}
                }
                return null;
            }""")

            price = None
            orig_price = None
            name = None
            product_url = None

            if jsonld:
                try:
                    data = json.loads(jsonld)
                    price = float(data.get("offers", {}).get("price", 0))
                    name = data.get("name")
                    product_url = data.get("offers", {}).get("url")
                except Exception:
                    pass

            # DOM fallback
            if not price:
                card = page.locator(
                    "[class*='product-item'], [class*='ProductCard'], [class*='ProductTile'], article"
                ).first

                for sel in ["[class*='price__main'], [class*='Price_price'], [class*='current']", "[class*='price']"]:
                    try:
                        price_text = await card.locator(sel).first.inner_text(timeout=1_500)
                        price = parse_price(price_text)
                        if price:
                            break
                    except PWTimeout:
                        continue

                for sel in ["[class*='was'], [class*='before'], del, s, [class*='original']"]:
                    try:
                        orig_text = await card.locator(sel).first.inner_text(timeout=1_000)
                        orig = parse_price(orig_text)
                        if orig and price and orig > price:
                            orig_price = orig
                        break
                    except PWTimeout:
                        continue

                if not name:
                    for sel in ["[class*='title'], [class*='name'], h3, h2"]:
                        try:
                            name = await card.locator(sel).first.inner_text(timeout=1_500)
                            if name:
                                break
                        except PWTimeout:
                            continue

                if not product_url:
                    try:
                        href = await card.locator("a").first.get_attribute("href", timeout=1_500)
                        product_url = f"{BASE}{href}" if href and not href.startswith("http") else href
                    except PWTimeout:
                        pass

            if not price:
                logger.warning(f"Penny: cenu se nepodařilo přečíst pro '{query}'")
                return None

            result = {
                "store_id": "penny",
                "price": price,
                "orig_price": orig_price,
                "product_name": (name or "").strip(),
                "url": product_url or search_url,
            }

        except PWTimeout as e:
            logger.warning(f"Penny timeout pro '{query}': {e}")
        except Exception as e:
            logger.error(f"Penny chyba pro '{query}': {e}", exc_info=True)
        finally:
            await browser.close()

    return result
