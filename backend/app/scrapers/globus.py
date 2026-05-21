"""
Globus.cz scraper

Z hlidac-shopu zdrojáků (extension/shops/globus.mjs):
  - Cena:     .money-price span.money-price__amount-discount  (sleva)
              nebo .money-price span.money-price__amount     (běžná)
  - Orig:     .money-price__amount--original
  - Název:    .title--product
  - Search:   /hledat?q=QUERY nebo /search?q=QUERY
"""
import json
import logging
from playwright.async_api import async_playwright, TimeoutError as PWTimeout
from .base import make_context, dismiss_cookies, parse_price

logger = logging.getLogger(__name__)

BASE = "https://www.globus.cz"


async def search_product(query: str) -> dict | None:
    search_url = f"{BASE}/hledat?q={query.replace(' ', '+')}"

    async with async_playwright() as pw:
        browser, context = await make_context(pw)
        page = await context.new_page()
        result = None
        try:
            await page.goto(search_url, wait_until="domcontentloaded", timeout=25_000)
            await dismiss_cookies(page)

            await page.wait_for_selector(
                "[class*='product-card'], [class*='ProductCard'], "
                "[class*='product-item'], .product-tile, article",
                timeout=12_000
            )

            card = page.locator(
                "[class*='product-card'], [class*='ProductCard'], "
                "[class*='product-item'], .product-tile, article"
            ).first

            # Název — .title--product (z extension kódu)
            name = None
            for sel in [".title--product", "[class*='title'], [class*='name']", "h3", "h2"]:
                try:
                    name = await card.locator(sel).first.inner_text(timeout=1_500)
                    if name:
                        break
                except PWTimeout:
                    continue

            # Cena (preferuj slevovou, pak běžnou)
            price = None
            for sel in [
                ".money-price span.money-price__amount-discount",
                ".money-price span.money-price__amount",
                "[class*='price__discount']",
                "[class*='price']",
            ]:
                try:
                    price_text = await card.locator(sel).first.inner_text(timeout=1_500)
                    price = parse_price(price_text)
                    if price:
                        break
                except PWTimeout:
                    continue

            if not price:
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
                if jsonld:
                    try:
                        data = json.loads(jsonld)
                        price = float(data.get("offers", {}).get("price", 0))
                        name = name or data.get("name")
                    except Exception:
                        pass

            if not price:
                logger.warning(f"Globus: cenu se nepodařilo přečíst pro '{query}'")
                return None

            # Původní cena
            orig_price = None
            for sel in [".money-price__amount--original", "[class*='original']", "del", "s"]:
                try:
                    orig_text = await card.locator(sel).first.inner_text(timeout=1_000)
                    orig = parse_price(orig_text)
                    if orig and orig > price:
                        orig_price = orig
                    break
                except PWTimeout:
                    continue

            product_url = None
            try:
                href = await card.locator("a").first.get_attribute("href", timeout=1_500)
                product_url = f"{BASE}{href}" if href and not href.startswith("http") else href
            except PWTimeout:
                pass

            result = {
                "store_id": "globus",
                "price": price,
                "orig_price": orig_price,
                "product_name": (name or "").strip(),
                "url": product_url,
            }

        except PWTimeout as e:
            logger.warning(f"Globus timeout pro '{query}': {e}")
        except Exception as e:
            logger.error(f"Globus chyba pro '{query}': {e}", exc_info=True)
        finally:
            await browser.close()

    return result
