"""
Billa.cz scraper

Z hlidac-shopu zdrojáků (extension/shops/billa.mjs):
  - JSON-LD v <script type="application/ld+json"> (ne data-hid)
  - data.sku = itemId, data.name = název, data.offers.price = cena
  - Cena per ks: .ws-product-price-type > .caption
  - Přeškrtnutá cena: není v JSON-LD, hledáme v DOM

Search URL: /hledat?q=QUERY nebo /search?q=QUERY
"""
import json
import re
import logging
from playwright.async_api import async_playwright, TimeoutError as PWTimeout
from .base import make_context, dismiss_cookies, parse_price

logger = logging.getLogger(__name__)

BASE = "https://www.billa.cz"


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
                "[class*='ws-product'], [class*='ProductCard'], "
                "[class*='product-item'], article",
                timeout=12_000
            )

            # Zkus JSON-LD ze stránky (nejspolehlivější)
            jsonld = await page.evaluate("""() => {
                for (const s of document.querySelectorAll('script[type="application/ld+json"]:not([data-hid])')) {
                    try {
                        const d = JSON.parse(s.textContent);
                        if (d['@type'] === 'Product') return s.textContent;
                        if (Array.isArray(d)) {
                            const p = d.find(x => x['@type'] === 'Product');
                            if (p) return JSON.stringify(p);
                        }
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
                    # priceSpecification může obsahovat původní cenu
                    price_spec = data.get("offers", {}).get("priceSpecification", {})
                    spec_price = price_spec.get("price") if isinstance(price_spec, dict) else None
                    if spec_price and float(spec_price) > price:
                        orig_price = float(spec_price)
                    product_url = data.get("offers", {}).get("url") or data.get("url")
                except Exception as e:
                    logger.debug(f"Billa JSON-LD parse: {e}")

            # DOM fallback
            if not price:
                card = page.locator("[class*='ws-product'], [class*='product-item'], article").first
                for sel in [".ws-product-price-type__value", "[class*='price']"]:
                    try:
                        price_text = await card.locator(sel).first.inner_text(timeout=1_500)
                        price = parse_price(price_text)
                        if price:
                            break
                    except PWTimeout:
                        continue

                for sel in ["[class*='original']", "del", "s", ".strikethrough"]:
                    try:
                        orig_text = await card.locator(sel).first.inner_text(timeout=1_000)
                        orig = parse_price(orig_text)
                        if orig and orig > price:
                            orig_price = orig
                        break
                    except PWTimeout:
                        continue

                if not name:
                    for sel in ["[class*='title'], [class*='name']", "h3"]:
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
                logger.warning(f"Billa: cenu se nepodařilo přečíst pro '{query}'")
                return None

            result = {
                "store_id": "billa",
                "price": price,
                "orig_price": orig_price,
                "product_name": (name or "").strip(),
                "url": product_url or search_url,
            }

        except PWTimeout as e:
            logger.warning(f"Billa timeout pro '{query}': {e}")
        except Exception as e:
            logger.error(f"Billa chyba pro '{query}': {e}", exc_info=True)
        finally:
            await browser.close()

    return result
