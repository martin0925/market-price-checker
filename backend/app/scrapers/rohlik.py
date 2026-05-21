"""
Rohlík.cz scraper — Playwright + JSON API

Klíčové endpointy (z hlidac-shopu zdrojáků):
  Navigace:  GET /services/frontend-service/renderer/navigation/flat.json
  Produkty:  GET /api/v1/products?products=ID1&products=ID2
  Ceny:      GET /api/v1/products/prices?products=ID1&...
  Search:    GET /api/v1/categories/normal/{catId}/products?page=N

Přístup: Rohlík vyžaduje cookies ze session. Playwright načte stránku,
získá session cookies, pak volá JSON API přímo.
"""
import json
import logging
from playwright.async_api import async_playwright, TimeoutError as PWTimeout
from .base import make_context, dismiss_cookies, parse_price

logger = logging.getLogger(__name__)

BASE = "https://www.rohlik.cz"


async def search_product(query: str) -> dict | None:
    async with async_playwright() as pw:
        browser, context = await make_context(pw)
        page = await context.new_page()
        result = None
        try:
            # 1) Načti search stránku – získáme session cookies a výsledky
            url = f"{BASE}/hledat?query={query.replace(' ', '+')}"
            await page.goto(url, wait_until="domcontentloaded", timeout=25_000)
            await dismiss_cookies(page)

            # 2) Počkej na product karty
            await page.wait_for_selector("#productDetail, [data-test='product-card'], article", timeout=12_000)

            # 3) Zachyť JSON API odpověď — Rohlík volá /api/v1/products při search
            #    Alternativně parsuj JSON-LD z prvního produktu
            #
            # Strategie A: přečti data z DOM (JSON-LD nebo data atributy)
            # Rohlik vkládá strukturovaná data do <script application/ld+json>

            # Zkus najít product cards a přečíst ceny z DOM
            card = page.locator('[data-test="product-card"]').first
            if not await card.count():
                # Zkus alternativní selektory
                card = page.locator('article[class*="product"]').first

            if not await card.count():
                logger.warning(f"Rohlík: žádné výsledky pro '{query}'")
                return None

            # Název produktu
            name = None
            for name_sel in ['[data-test="product-card-name"]', 'h3', 'h2', '[class*="name"]']:
                try:
                    name = await card.locator(name_sel).first.inner_text(timeout=2_000)
                    if name:
                        break
                except PWTimeout:
                    continue

            # Cena — primárně zkus JSON-LD na stránce
            price = None
            orig_price = None
            product_url = None

            # JSON-LD ze stránky
            jsonld_text = await page.evaluate("""() => {
                const scripts = document.querySelectorAll('script[type="application/ld+json"]');
                for (const s of scripts) {
                    try {
                        const d = JSON.parse(s.textContent);
                        if (d['@type'] === 'Product' || (Array.isArray(d) && d[0]?.['@type'] === 'Product')) {
                            return s.textContent;
                        }
                    } catch(e) {}
                }
                return null;
            }""")

            if jsonld_text:
                try:
                    data = json.loads(jsonld_text)
                    if isinstance(data, list):
                        data = data[0]
                    price = float(data.get("offers", {}).get("price", 0))
                    name = data.get("name", name)
                    product_url = data.get("offers", {}).get("url")
                except Exception as e:
                    logger.debug(f"Rohlík JSON-LD parse chyba: {e}")

            # Fallback: čti cenu z DOM
            if not price:
                for price_sel in [
                    '[data-test="product-card-price"]',
                    '[class*="Price_fullPrice"]',
                    '[class*="price--full"]',
                    '.currentPrice',
                    '.actionPrice',
                    '[class*="price"]',
                ]:
                    try:
                        price_text = await card.locator(price_sel).first.inner_text(timeout=1_500)
                        price = parse_price(price_text)
                        if price:
                            break
                    except PWTimeout:
                        continue

            if not price:
                logger.warning(f"Rohlík: cenu se nepodařilo přečíst pro '{query}'")
                return None

            # Přeškrtnutá cena (sleva)
            for orig_sel in [
                '[data-test="product-card-price-original"]',
                'del',
                '[class*="strikethrough"]',
                '[class*="originalPrice"]',
                '[class*="crossed"]',
            ]:
                try:
                    orig_text = await card.locator(orig_sel).first.inner_text(timeout=1_000)
                    orig = parse_price(orig_text)
                    if orig and orig > price:
                        orig_price = orig
                    break
                except PWTimeout:
                    continue

            # URL
            if not product_url:
                try:
                    href = await card.locator("a").first.get_attribute("href", timeout=1_500)
                    product_url = f"{BASE}{href}" if href and not href.startswith("http") else href
                except PWTimeout:
                    pass

            result = {
                "store_id": "rohlik",
                "price": price,
                "orig_price": orig_price,
                "product_name": (name or "").strip(),
                "url": product_url,
            }

        except PWTimeout as e:
            logger.warning(f"Rohlík timeout pro '{query}': {e}")
        except Exception as e:
            logger.error(f"Rohlík chyba pro '{query}': {e}", exc_info=True)
        finally:
            await browser.close()

    return result
