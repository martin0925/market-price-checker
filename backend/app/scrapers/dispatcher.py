"""
Dispatcher: fetchuje ceny z produktových URL a ukládá do DB.

Každý item má v tabulce product_links seznam přímých URL (různé varianty/obchody).
Pro každý link se zavolá get_price_from_url — store-specifická nebo generická z base.py.
Výsledky se ukládají do price_history; pro každý obchod se zobrazuje nejlevnější varianta.
"""
import asyncio
import logging
import sys
from concurrent.futures import ThreadPoolExecutor
from app.database import get_conn

logger = logging.getLogger(__name__)

# Na Windows uvicorn event loop nepodporuje subprocesy (Playwright).
# Každý scraper běží ve vlákně s vlastním asyncio.run() → ProactorEventLoop.
_executor = ThreadPoolExecutor(max_workers=1)


async def _call_scraper(fn, url: str):
    if sys.platform != "win32":
        return await fn(url)
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, lambda: asyncio.run(fn(url)))


def _get_price_fn(store_id: str):
    """Vrátí get_price_from_url pro daný obchod — store-specifická nebo generická."""
    store_modules = {
        "rohlik":   "app.scrapers.rohlik",
        "kosik":    "app.scrapers.kosik",
        "kaufland": "app.scrapers.kaufland",
        "albert":   "app.scrapers.albert",
        "billa":    "app.scrapers.billa",
        "lidl":     "app.scrapers.lidl",
        "penny":    "app.scrapers.penny",
        "globus":   "app.scrapers.globus",
        "tesco":    "app.scrapers.tesco",
    }
    mod_path = store_modules.get(store_id)
    if mod_path:
        try:
            import importlib
            mod = importlib.import_module(mod_path)
            fn = getattr(mod, "get_price_from_url", None)
            if fn:
                return fn
        except Exception:
            pass
    from app.scrapers.base import get_price_from_url
    return get_price_from_url


async def refresh_item(item_id: int) -> dict:
    conn = get_conn()
    item = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if not item:
        conn.close()
        return {"item_id": item_id, "item_name": "?", "scraped": 0, "errors": ["Item nenalezen"]}

    links = conn.execute(
        "SELECT * FROM product_links WHERE item_id = ? AND active = 1",
        (item_id,)
    ).fetchall()
    conn.close()

    if not links:
        return {
            "item_id": item_id,
            "item_name": item["name"],
            "scraped": 0,
            "errors": ["Žádné produktové odkazy — přidej je v UI"],
        }

    scraped = 0
    errors = []

    for link in links:
        store_id = link["store_id"]
        url = link["url"]
        label = link["label"] or ""
        fn = _get_price_fn(store_id)

        try:
            logger.info(f"Fetchuji {store_id}: {url[:70]}...")
            data = await _call_scraper(fn, url)
        except Exception as e:
            logger.error(f"Chyba {store_id} ({label}): {e}")
            errors.append(f"{store_id}: {e}")
            continue

        if not data or not data.get("price"):
            errors.append(f"{store_id} ({label or url[:50]}): žádný výsledek")
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
                    data.get("product_name") or label, url,
                ),
            )
            conn.commit()
            scraped += 1
            logger.info(f"  ✓ {store_id}: {data['price']} Kč ({(data.get('product_name') or label)[:40]})")
        finally:
            conn.close()

        await asyncio.sleep(1.5)

    return {
        "item_id": item_id,
        "item_name": item["name"],
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
        await asyncio.sleep(2)

    return results
