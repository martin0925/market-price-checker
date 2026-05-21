"""
Dispatcher: spouští scrapery pro povolené obchody a ukládá ceny do DB.

Každý scraper běží v samostatném procesu (ProcessPoolExecutor) aby izoloval
Playwright instance a zabránil memory leakům při dlouhém běhu.
Playwright má problém s asyncio.gather() — sdílené event looopy crashují.
Proto scrapy voláme sériově s malou pauzou.
"""
import asyncio
import logging
from datetime import datetime
from app.database import get_conn

logger = logging.getLogger(__name__)

# Registry: store_id -> modul
def _get_scraper(store_id: str):
    if store_id == "rohlik":
        from app.scrapers.rohlik import search_product
    elif store_id == "kosik":
        from app.scrapers.kosik import search_product
    elif store_id == "kaufland":
        from app.scrapers.kaufland import search_product
    elif store_id == "albert":
        from app.scrapers.albert import search_product
    elif store_id == "billa":
        from app.scrapers.billa import search_product
    elif store_id == "lidl":
        from app.scrapers.lidl import search_product
    elif store_id == "penny":
        from app.scrapers.penny import search_product
    elif store_id == "globus":
        from app.scrapers.globus import search_product
    elif store_id == "tesco":
        from app.scrapers.tesco import search_product
    else:
        return None
    return search_product


IMPLEMENTED = {"rohlik", "kosik", "kaufland", "albert", "billa", "lidl", "penny", "globus", "tesco"}


async def refresh_item(item_id: int) -> dict:
    conn = get_conn()
    item = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if not item:
        conn.close()
        return {"item_id": item_id, "item_name": "?", "scraped": 0, "errors": ["Item nenalezen"]}

    enabled = conn.execute(
        "SELECT id FROM stores WHERE enabled = 1"
    ).fetchall()
    conn.close()

    store_ids = [r["id"] for r in enabled if r["id"] in IMPLEMENTED]
    query = item["query"]
    item_name = item["name"]

    scraped = 0
    errors = []

    # Sériové spouštění — Playwright nesnáší sdílený event loop mezi instancemi
    for store_id in store_ids:
        fn = _get_scraper(store_id)
        if not fn:
            continue
        try:
            logger.info(f"Scrapuji {store_id} pro '{query}'...")
            data = await fn(query)
        except Exception as e:
            logger.error(f"Scraper {store_id} selhal pro '{query}': {e}")
            errors.append(f"{store_id}: {e}")
            continue

        if not data or not data.get("price"):
            errors.append(f"{store_id}: žádný výsledek pro '{query}'")
            continue

        conn = get_conn()
        try:
            conn.execute(
                """INSERT INTO price_history
                   (item_id, store_id, price, orig_price, product_name, url)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    item_id, store_id,
                    data["price"], data.get("orig_price"),
                    data.get("product_name"), data.get("url"),
                ),
            )
            conn.commit()
            scraped += 1
            logger.info(f"  ✓ {store_id}: {data['price']} Kč ({data.get('product_name', '')[:40]})")
        finally:
            conn.close()

        # Pauza mezi obchody (rate limiting)
        await asyncio.sleep(1.5)

    return {
        "item_id": item_id,
        "item_name": item_name,
        "scraped": scraped,
        "errors": errors,
    }


async def refresh_all_items() -> list[dict]:
    conn = get_conn()
    items = conn.execute("SELECT id FROM items").fetchall()
    conn.close()

    results = []
    for row in items:
        r = await refresh_item(row["id"])
        results.append(r)
        await asyncio.sleep(2)  # pauza mezi itemy

    return results
