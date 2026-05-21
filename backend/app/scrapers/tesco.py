"""
Tesco.cz (iTesco) scraper

Z hlidac-shopu zdrojáků (extension/shops/itesco.mjs):
  - Cena:   .price-per-sellable-unit .value
  - Název:  h1
  - Sleva:  .promo-content-small .offer-text (text parsovat)
  - ID:     z URL /(\\d+)$ 
  - Search: https://www.tesco.cz/groceries/cs-CZ/search?query=QUERY
           nebo https://nakup.itesco.cz/cs-CZ/groceries/search?query=QUERY

iTesco je Akamai chráněný — může být nutný retry nebo session warming.
"""
import json
import logging
from playwright.async_api import async_playwright, TimeoutError as PWTimeout
from .base import make_context, dismiss_cookies, parse_price

logger = logging.getLogger(__name__)

# iTesco CZ URL
BASE = "https://nakup.itesco.cz"
ALT_BASE = "https://www.tesco.cz"


async def search_product(query: str) -> dict | None:
    search_urls = [
        f"{BASE}/cs-CZ/groceries/search?query={query.replace(' ', '+')}",
        f"{ALT_BASE}/groceries/cs-CZ/search?query={query.replace(' ', '+')}",
    ]

    async with async_playwright() as pw:
        browser, context = await make_context(pw)
        page = await context.new_page()
        result = None
        try:
            loaded = False
            search_url = search_urls[0]
            for url in search_urls:
                try:
                    resp = await page.goto(url, wait_until="domcontentloaded", timeout=25_000)
                    if resp and resp.status < 400:
                        loaded = True
                        search_url = url
                        break
                except Exception:
                    continue

            if not loaded:
                logger.warning(f"Tesco: nepodařilo se načíst search pro '{query}'")
                return None

            await dismiss_cookies(page)

            # Tesco renderuje produkty jako .product-list--list-item nebo .tile-link
            await page.wait_for_selector(
                ".product-list--list-item, [class*='product-item'], "
                ".tile-link, [class*='ProductCard'], article",
                timeout=12_000
            )

            card = page.locator(
                ".product-list--list-item, [class*='product-item'], article"
            ).first

            # Název
            name = None
            for sel in [
                "[class*='product-details--title']",
                ".tile-link span",
                "h3", "h2",
                "[class*='title'], [class*='name']",
            ]:
                try:
                    name = await card.locator(sel).first.inner_text(timeout=1_500)
                    if name:
                        break
                except PWTimeout:
                    continue

            # Cena — .price-per-sellable-unit .value
            price = None
            for sel in [
                ".price-per-sellable-unit .value",
                ".price-per-sellable-unit",
                "[class*='price__value']",
                "[class*='price']",
            ]:
                try:
                    price_text = await card.locator(sel).first.inner_text(timeout=1_500)
                    price = parse_price(price_text)
                    if price:
                        break
                except PWTimeout:
                    continue

            # Zkus JSON-LD pokud DOM selhal
            if not price:
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
                logger.warning(f"Tesco: cenu se nepodařilo přečíst pro '{query}'")
                return None

            # Původní cena (Tesco zobrazuje slevy jako promo text)
            orig_price = None
            for sel in ["del", "s", "[class*='was-price'], [class*='original']"]:
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
                base = BASE if BASE in search_url else ALT_BASE
                product_url = f"{base}{href}" if href and not href.startswith("http") else href
            except PWTimeout:
                pass

            result = {
                "store_id": "tesco",
                "price": price,
                "orig_price": orig_price,
                "product_name": (name or "").strip(),
                "url": product_url,
            }

        except PWTimeout as e:
            logger.warning(f"Tesco timeout pro '{query}': {e}")
        except Exception as e:
            logger.error(f"Tesco chyba pro '{query}': {e}", exc_info=True)
        finally:
            await browser.close()

    return result
