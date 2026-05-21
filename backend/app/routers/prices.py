from fastapi import APIRouter, HTTPException, BackgroundTasks
from app.database import get_conn
from app.scrapers.dispatcher import refresh_item, refresh_all_items
from app.schemas import RefreshResult

router = APIRouter()


@router.post("/refresh/{item_id}", response_model=RefreshResult)
async def trigger_refresh(item_id: int):
    """Aktualizuje ceny pro jeden item (synchronně, čeká na výsledek)."""
    conn = get_conn()
    if not conn.execute("SELECT id FROM items WHERE id = ?", (item_id,)).fetchone():
        conn.close()
        raise HTTPException(404, "Item nenalezen")
    conn.close()
    return await refresh_item(item_id)


@router.post("/refresh-all")
async def trigger_refresh_all(background_tasks: BackgroundTasks):
    """Spustí refresh všech itemů na pozadí."""
    background_tasks.add_task(refresh_all_items)
    return {"status": "started", "message": "Refresh spuštěn na pozadí"}


@router.get("/history/{item_id}")
def get_history(item_id: int, store_id: str | None = None, days: int = 30):
    """Vrátí historii cen pro item (volitelně filtrovat dle store)."""
    conn = get_conn()
    if not conn.execute("SELECT id FROM items WHERE id = ?", (item_id,)).fetchone():
        conn.close()
        raise HTTPException(404, "Item nenalezen")

    query = """
        SELECT ph.*, s.name as store_name
        FROM price_history ph
        JOIN stores s ON s.id = ph.store_id
        WHERE ph.item_id = ?
          AND ph.fetched_at >= datetime('now', ? || ' days')
    """
    params = [item_id, f"-{days}"]

    if store_id:
        query += " AND ph.store_id = ?"
        params.append(store_id)

    query += " ORDER BY ph.fetched_at DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()

    return [
        {
            "store_id": r["store_id"],
            "store_name": r["store_name"],
            "price": r["price"],
            "orig_price": r["orig_price"],
            "on_sale": r["orig_price"] is not None,
            "product_name": r["product_name"],
            "url": r["url"],
            "fetched_at": r["fetched_at"],
        }
        for r in rows
    ]


@router.get("/summary/basket")
def basket_summary():
    """Nejlevnější košík - součet nejnižší aktuální ceny per store."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT s.id as store_id, s.name as store_name,
               SUM(ph.price) as total,
               COUNT(ph.id) as items_covered,
               SUM(ph.orig_price IS NOT NULL) as sale_count
        FROM stores s
        JOIN price_history ph ON ph.store_id = s.id
        WHERE ph.fetched_at = (
            SELECT MAX(ph2.fetched_at) FROM price_history ph2
            WHERE ph2.item_id = ph.item_id AND ph2.store_id = ph.store_id
        )
        GROUP BY s.id
        ORDER BY total ASC
    """).fetchall()
    conn.close()

    return [
        {
            "store_id": r["store_id"],
            "store_name": r["store_name"],
            "total": round(r["total"], 2),
            "items_covered": r["items_covered"],
            "sale_count": r["sale_count"],
        }
        for r in rows
    ]
