"""
Kaufland.cz scraper — HTML + JSON-LD

Z hlidac-shopu zdrojáků:
  - Produkty jsou v <script data-n-head> jako JSON Array s @type: "Product"
  - Selektory: article.product, .product__title, .price-note--rrp (přeškrtnutá)
  - Cena z JSON-LD: product.offers.price
  - Přeškrtnutá: .price-note--rrp (cleanPrice)
  - Search URL: /search?search=QUERY

Kaufland neblokuje httpx (nepoužívá Cloudflare agresivně),
zkusíme nejdřív přímý HTTP request a fallback Playwright.
"""
import httpx
import json
import re
import logging
from playwright.async_api import async_playwright, TimeoutError as PWTimeout
from .base import make_context, dismiss_cookies, parse_price

logger = logging.getLogger(__name__)

BASE = "https://www.kaufland.cz"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "cs-CZ,cs;q=0.9",
}


def _extract_from_jsonld(html: str) -> dict | None:
    """Extrahuje první produkt z JSON-LD v HTML."""
    # <script data-n-head ...> s @type Product
    matches = re.findall(
        r'<script[^>]*data-n-head[^>]*>(.*?)</script>',
        html, re.DOTALL
    )
    for match in matches:
        try:
            data = json.loads(match)
            products = data if isinstance(data, list) else [data]
            for p in products:
                if p.get("@type") == "Product":
                    price = float(p.get("offers", {}).get("price", 0))
                    name = p.get("name", "")
                    url = p.get("offers", {}).get("url", "")
                    return {"price": price, "name": name, "url": url}
        except Exception:
            continue

    # Fallback: <script type="application/ld+json">
    matches2 = re.findall(
        r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>',
        html, re.DOTALL
    )
    for match in matches2:
        try:
            data = json.loads(match)
            if isinstance(data, list):
                for p in data:
                    if p.get("@type") == "Product":
                        price = float(p.get("offers", {}).get("price", 0))
                        return {"price": price, "name": p.get("name",""), "url": p.get("offers",{}).get("url","")}
        except Exception:
            continue
    return None


def _extract_discount(html: str) -> float | None:
    """Hledá přeškrtnutou cenu (.price-note--rrp)."""
    m = re.search(r'price-note--rrp[^>]*>([^<]+)<', html)
    if m:
        return parse_price(m.group(1))
    return None


async def get_price_from_url(url: str) -> dict | None:
    """Přímý fetch produktové stránky Kaufland — bez Playwright (httpx)."""
    try:
        async with httpx.AsyncClient(timeout=12, follow_redirects=True, headers=HEADERS) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                html = resp.text
                product = _extract_from_jsonld(html)
                if product and product["price"]:
                    orig = _extract_discount(html)
                    return {
                        "price": product["price"],
                        "orig_price": orig if orig and orig > product["price"] else None,
                        "product_name": product["name"],
                        "url": url,
                    }
    except Exception as e:
        logger.debug(f"Kaufland get_price_from_url HTTP fallback na Playwright: {e}")

    # Playwright fallback
    from .base import get_price_from_url as _generic
    return await _generic(url)


async def search_product(query: str) -> dict | None:
    search_url = f"{BASE}/search?search={query.replace(' ', '+')}"

    # Zkus nejdřív přímý HTTP (rychlejší, nezatěžuje Playwright)
    try:
        async with httpx.AsyncClient(timeout=12, follow_redirects=True, headers=HEADERS) as client:
            resp = await client.get(search_url)
            if resp.status_code == 200:
                html = resp.text
                product = _extract_from_jsonld(html)
                if product and product["price"]:
                    orig = _extract_discount(html)
                    return {
                        "store_id": "kaufland",
                        "price": product["price"],
                        "orig_price": orig if orig and orig > product["price"] else None,
                        "product_name": product["name"],
                        "url": product["url"] or search_url,
                    }
    except Exception as e:
        logger.debug(f"Kaufland HTTP fallback na Playwright: {e}")

    # Playwright fallback
    async with async_playwright() as pw:
        browser, context = await make_context(pw)
        page = await context.new_page()
        result = None
        try:
            await page.goto(search_url, wait_until="domcontentloaded", timeout=25_000)
            await dismiss_cookies(page)
            await page.wait_for_selector("article.product, [class*='product-tile']", timeout=12_000)

            html = await page.content()
            product = _extract_from_jsonld(html)
            if not product:
                # DOM fallback — čti z article.product
                card = page.locator("article.product").first
                name = await card.locator(".product__title").first.inner_text(timeout=2_000)
                price_text = await card.locator(".product__price-info, [class*='price']").first.inner_text(timeout=2_000)
                price = parse_price(price_text)
                orig_text = None
                try:
                    orig_text = await card.locator(".price-note--rrp").first.inner_text(timeout=1_000)
                except PWTimeout:
                    pass
                orig_price = parse_price(orig_text) if orig_text else None
                href = await card.locator("a").first.get_attribute("href", timeout=1_500)
                url = f"{BASE}{href}" if href and not href.startswith("http") else href
                result = {
                    "store_id": "kaufland", "price": price,
                    "orig_price": orig_price if orig_price and orig_price > price else None,
                    "product_name": name.strip(), "url": url,
                }
            else:
                orig = _extract_discount(html)
                result = {
                    "store_id": "kaufland",
                    "price": product["price"],
                    "orig_price": orig if orig and orig > product["price"] else None,
                    "product_name": product["name"],
                    "url": product["url"] or search_url,
                }
        except PWTimeout as e:
            logger.warning(f"Kaufland timeout pro '{query}': {e}")
        except Exception as e:
            logger.error(f"Kaufland chyba pro '{query}': {e}", exc_info=True)
        finally:
            await browser.close()

    return result
