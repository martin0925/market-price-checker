"""
Košík.cz scraper — JSON API (bez auth)

Klíčové endpointy (z hlidac-shopu zdrojáků):
  Kategorie: GET /api/front/menu/main
  Produkty:  GET /api/front/page/products?slug=SLUG&limit=30
  Search:    GET /hledat?q=QUERY  (HTML, ale producty jsou v JSON <script>)

Struktura produktu v API:
  { id, name, url, price, recommendedPrice, percentageDiscount, image,
    pricePerUnit: {price}, productQuantity: {value, prefix} }
"""
import json
import logging
from playwright.async_api import async_playwright, TimeoutError as PWTimeout
from .base import make_context, dismiss_cookies, parse_price

logger = logging.getLogger(__name__)

BASE = "https://www.kosik.cz"


async def search_product(query: str) -> dict | None:
    async with async_playwright() as pw:
        browser, context = await make_context(pw)
        page = await context.new_page()
        result = None

        # Zachytávej API odpovědi
        api_data = {}

        async def handle_response(response):
            if "/api/front/page/products" in response.url or "/api/front/search" in response.url:
                try:
                    data = await response.json()
                    api_data["products"] = data
                except Exception:
                    pass

        page.on("response", handle_response)

        try:
            url = f"{BASE}/hledat?q={query.replace(' ', '+')}"
            await page.goto(url, wait_until="networkidle", timeout=25_000)
            await dismiss_cookies(page)

            # Pokud máme data z API interceptu, použij je
            if api_data.get("products"):
                items = (
                    api_data["products"].get("products", {}).get("items")
                    or api_data["products"].get("items")
                    or []
                )
                if items:
                    p = items[0]
                    price = p.get("price")
                    rec_price = p.get("recommendedPrice")
                    orig_price = rec_price if rec_price and rec_price > price else None
                    slug = p.get("url", "").lstrip("/")
                    result = {
                        "store_id": "kosik",
                        "price": float(price) if price else None,
                        "orig_price": float(orig_price) if orig_price else None,
                        "product_name": p.get("name", ""),
                        "url": f"{BASE}/{slug}" if slug else None,
                    }
                    if result["price"]:
                        return result

            # Fallback: přečti ze stránky
            # Košík renderuje produkty v [data-tid=product-list]
            await page.wait_for_selector(
                "[data-tid=product-list] [data-tid=product-box], "
                "[class*='ProductList'] article, "
                "article[data-tid]",
                timeout=12_000
            )

            card = page.locator(
                "[data-tid=product-list] [data-tid=product-box], "
                "article[data-tid]"
            ).first

            # Název
            name = None
            for sel in ["[data-tid=product-box__name]", "[data-tid*=name]", "h3", "h2"]:
                try:
                    name = await card.locator(sel).first.inner_text(timeout=1_500)
                    if name:
                        break
                except PWTimeout:
                    continue

            # Cena — Košík zobrazuje v [data-tid=pbox-price]
            # Struktura: <span><span>32</span><span>90</span></span>
            price = None
            for sel in ["[data-tid=pbox-price]", "[data-tid*=price]", "[class*='price']"]:
                try:
                    price_text = await card.locator(sel).first.inner_text(timeout=1_500)
                    price = parse_price(price_text)
                    if price:
                        break
                except PWTimeout:
                    continue

            if not price:
                logger.warning(f"Košík: cenu se nepodařilo přečíst pro '{query}'")
                return None

            # Původní cena (přeškrtnutá)
            orig_price = None
            for sel in ["[data-tid=product-box__crossed-price]", "[class*='crossed']", "del", "s"]:
                try:
                    orig_text = await card.locator(sel).first.inner_text(timeout=1_000)
                    orig = parse_price(orig_text)
                    if orig and orig > price:
                        orig_price = orig
                    break
                except PWTimeout:
                    continue

            # URL
            product_url = None
            try:
                href = await card.locator("a").first.get_attribute("href", timeout=1_500)
                product_url = f"{BASE}{href}" if href and not href.startswith("http") else href
            except PWTimeout:
                pass

            result = {
                "store_id": "kosik",
                "price": price,
                "orig_price": orig_price,
                "product_name": (name or "").strip(),
                "url": product_url,
            }

        except PWTimeout as e:
            logger.warning(f"Košík timeout pro '{query}': {e}")
        except Exception as e:
            logger.error(f"Košík chyba pro '{query}': {e}", exc_info=True)
        finally:
            await browser.close()

    return result
