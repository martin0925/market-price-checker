"""
Albert.cz scraper

Z hlidac-shopu zdrojáků (extension/shops/albert.mjs):
  - Cena je v [data-testid=product-block-price] v HALÉŘích → dělíme 100
  - JSON-LD v #product-details-seo-data (na detail stránce)
  - offers.priceSpecification.price = původní cena
  - Search URL: /hledat/?q=QUERY nebo /hledat/QUERY

Selektory search stránky:
  - Produkty: [data-testid=product-list-item] nebo [data-testid=product-block]
"""
import json
import re
import logging
from playwright.async_api import async_playwright, TimeoutError as PWTimeout
from .base import make_context, dismiss_cookies, parse_price

logger = logging.getLogger(__name__)

BASE = "https://www.albert.cz"


def _price_from_halers(text: str) -> float | None:
    """Albert vrací ceny v haléřích (např. '3290' = 32,90 Kč)."""
    nums = re.findall(r'\d+', text.replace("\xa0", "").replace(" ", ""))
    if not nums:
        return None
    val = int("".join(nums))
    # Pokud je hodnota větší než 10000, je v haléřích
    return val / 100 if val > 1000 else float(val)


async def search_product(query: str) -> dict | None:
    search_url = f"{BASE}/hledat/?q={query.replace(' ', '+')}"

    async with async_playwright() as pw:
        browser, context = await make_context(pw)
        page = await context.new_page()
        result = None
        try:
            await page.goto(search_url, wait_until="domcontentloaded", timeout=25_000)
            await dismiss_cookies(page)

            await page.wait_for_selector(
                "[data-testid=product-list-item], [data-testid=product-block], "
                "[class*='ProductCard'], article",
                timeout=12_000
            )

            card = page.locator(
                "[data-testid=product-list-item], [data-testid=product-block]"
            ).first

            # Název
            name = None
            for sel in [
                "[data-testid=product-block-name]",
                "[data-testid*=name]",
                "h3", "h2",
            ]:
                try:
                    name = await card.locator(sel).first.inner_text(timeout=1_500)
                    if name:
                        break
                except PWTimeout:
                    continue

            # Cena — Albert ji ukládá jako integer haléřů nebo string s Kč
            price = None
            for sel in [
                "[data-testid=product-block-price]",
                "[data-testid*=price]",
                "[class*='Price']",
            ]:
                try:
                    price_text = await card.locator(sel).first.inner_text(timeout=1_500)
                    price = _price_from_halers(price_text)
                    if not price:
                        price = parse_price(price_text)
                    if price:
                        break
                except PWTimeout:
                    continue

            if not price:
                logger.warning(f"Albert: cenu se nepodařilo přečíst pro '{query}'")
                return None

            # Původní cena
            orig_price = None
            for sel in [
                "[data-testid*=original], [data-testid*=was]",
                "del", "s", "[class*='original']",
            ]:
                try:
                    orig_text = await card.locator(sel).first.inner_text(timeout=1_000)
                    orig = _price_from_halers(orig_text) or parse_price(orig_text)
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
                "store_id": "albert",
                "price": price,
                "orig_price": orig_price,
                "product_name": (name or "").strip(),
                "url": product_url,
            }

        except PWTimeout as e:
            logger.warning(f"Albert timeout pro '{query}': {e}")
        except Exception as e:
            logger.error(f"Albert chyba pro '{query}': {e}", exc_info=True)
        finally:
            await browser.close()

    return result
