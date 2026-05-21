"""
Lidl.cz scraper — Playwright (SPA, Nuxt)

Z hlidac-shopu zdrojáků (actors/lidl-daily, extension/shops/lidl.mjs):
  - Lidl je Nuxt SPA — vyžaduje Playwright (JS render)
  - Produktová API: /q/api/category/CATPATH/CATID?offset=0&fetchsize=1000&locale=cs_CZ
  - Search: https://www.lidl.cz/q/query/QUERY
  - DOM selektory (extension):
      cena:     .detail-one .buybox-one .ods-price__value
      orig:     .buybox-one .ods-price__stroke-price s
      název:    .detail-one [data-qa-label='keyfacts-title']
  - Search stránka selektory:
      produkty: [selector="PRODUCT"] nebo .ods-tile
      cena:     .pricebox__price nebo .ods-price__value
      orig:     .pricebox__recommended-retail-price nebo .m-price__rrp
"""
import json
import logging
from playwright.async_api import async_playwright, TimeoutError as PWTimeout
from .base import make_context, dismiss_cookies, parse_price

logger = logging.getLogger(__name__)

BASE = "https://www.lidl.cz"


async def search_product(query: str) -> dict | None:
    # Lidl search URL format
    search_url = f"{BASE}/q/query/{query.replace(' ', '%20')}"

    async with async_playwright() as pw:
        browser, context = await make_context(pw)
        page = await context.new_page()
        result = None

        # Zachyť API odpovědi (Lidl volá /q/api/... při browsování)
        api_items = []
        async def handle_response(response):
            if "/q/api/" in response.url and "category" in response.url:
                try:
                    data = await response.json()
                    items = data.get("items", [])
                    api_items.extend(items)
                except Exception:
                    pass
        page.on("response", handle_response)

        try:
            await page.goto(search_url, wait_until="networkidle", timeout=30_000)
            await dismiss_cookies(page)

            # Počkej na produkty — Lidl je SPA, produkty se renderují async
            await page.wait_for_selector(
                '[selector="PRODUCT"], .ods-tile, article[class*="product"], '
                '.product-grid-box, [class*="ProductItem"]',
                timeout=15_000
            )

            # Strategie 1: Přečti data z JSON-LD nebo data atributů
            # Lidl vkládá data do data-gridbox-impression
            gridbox_data = await page.evaluate("""() => {
                const els = document.querySelectorAll('[data-gridbox-impression]');
                if (els.length === 0) return null;
                try {
                    return JSON.parse(decodeURIComponent(els[0].dataset.gridboxImpression));
                } catch(e) { return null; }
            }""")

            if gridbox_data:
                price = gridbox_data.get("price")
                item_id = gridbox_data.get("id", "")
                name = gridbox_data.get("name", "")

                # Přečti původní cenu z DOM (.m-price__rrp)
                orig_price = None
                try:
                    orig_text = await page.locator('[selector="PRODUCT"] .m-price__rrp').first.inner_text(timeout=2_000)
                    orig = parse_price(orig_text)
                    if orig and price and orig > price:
                        orig_price = orig
                except PWTimeout:
                    pass

                # URL produktu
                product_url = None
                try:
                    href = await page.locator('[selector="PRODUCT"] .ods-tile__link').first.get_attribute("href", timeout=1_500)
                    product_url = f"{BASE}{href}" if href and not href.startswith("http") else href
                except PWTimeout:
                    pass

                if price:
                    return {
                        "store_id": "lidl",
                        "price": float(price),
                        "orig_price": orig_price,
                        "product_name": name,
                        "url": product_url,
                    }

            # Strategie 2: DOM selektory
            card = page.locator(
                '[selector="PRODUCT"], .ods-tile, article[class*="product"]'
            ).first

            name = None
            for sel in [".ods-tile__title", "h3", "h2", "[class*='title']"]:
                try:
                    name = await card.locator(sel).first.inner_text(timeout=1_500)
                    if name:
                        break
                except PWTimeout:
                    continue

            price = None
            for sel in [".ods-price__value", ".pricebox__price", "[class*='price']"]:
                try:
                    price_text = await card.locator(sel).first.inner_text(timeout=1_500)
                    price = parse_price(price_text)
                    if price:
                        break
                except PWTimeout:
                    continue

            if not price:
                logger.warning(f"Lidl: cenu se nepodařilo přečíst pro '{query}'")
                return None

            orig_price = None
            for sel in [".ods-price__stroke-price", ".pricebox__recommended-retail-price", "del", "s"]:
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
                "store_id": "lidl",
                "price": price,
                "orig_price": orig_price,
                "product_name": (name or "").strip(),
                "url": product_url,
            }

        except PWTimeout as e:
            logger.warning(f"Lidl timeout pro '{query}': {e}")
        except Exception as e:
            logger.error(f"Lidl chyba pro '{query}': {e}", exc_info=True)
        finally:
            await browser.close()

    return result
