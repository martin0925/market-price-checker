from fastapi import APIRouter, HTTPException
from app.database import get_conn
from app.schemas import ItemCreate, ItemOut, ItemWithPrices, PriceEntry

router = APIRouter()


def _row_to_item(row) -> ItemOut:
    return ItemOut(
        id=row["id"],
        name=row["name"],
        unit=row["unit"],
        category=row["category"],
        created_at=row["created_at"],
    )


@router.get("/", response_model=list[ItemOut])
def list_items():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM items ORDER BY name").fetchall()
    conn.close()
    return [_row_to_item(r) for r in rows]


@router.post("/", response_model=ItemOut, status_code=201)
def create_item(body: ItemCreate):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO items (name, unit, category, query) VALUES (?,?,?,'') ",
        (body.name, body.unit, body.category),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM items WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return _row_to_item(row)


@router.get("/{item_id}", response_model=ItemWithPrices)
def get_item(item_id: int):
    conn = get_conn()
    item = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if not item:
        conn.close()
        raise HTTPException(404, "Item nenalezen")

    # Všechny záznamy seřazené od nejnovějšího
    rows = conn.execute(
        """SELECT ph.*, s.name as store_name
           FROM price_history ph
           JOIN stores s ON s.id = ph.store_id
           WHERE ph.item_id = ?
           ORDER BY ph.fetched_at DESC, ph.price ASC""",
        (item_id,),
    ).fetchall()
    conn.close()

    # Pro každý obchod: nejnovější den → nejlevnější varianta
    store_latest_date: dict[str, str] = {}
    store_best: dict[str, dict] = {}
    for r in rows:
        sid = r["store_id"]
        row_date = r["fetched_at"][:10]
        if sid not in store_latest_date:
            store_latest_date[sid] = row_date
        if row_date == store_latest_date[sid]:
            if sid not in store_best or r["price"] < store_best[sid]["price"]:
                store_best[sid] = dict(r)

    prices = [
        PriceEntry(
            store_id=r["store_id"],
            store_name=r["store_name"],
            price=r["price"],
            orig_price=r["orig_price"],
            on_sale=r["orig_price"] is not None,
            product_name=r["product_name"],
            url=r["url"],
            fetched_at=r["fetched_at"],
        )
        for r in sorted(store_best.values(), key=lambda x: x["price"])
    ]

    cheapest = prices[0] if prices else None
    return ItemWithPrices(
        item=_row_to_item(item),
        prices=prices,
        cheapest_store=cheapest.store_id if cheapest else None,
        cheapest_price=cheapest.price if cheapest else None,
    )


@router.delete("/{item_id}", status_code=204)
def delete_item(item_id: int):
    conn = get_conn()
    if not conn.execute("SELECT id FROM items WHERE id = ?", (item_id,)).fetchone():
        conn.close()
        raise HTTPException(404, "Item nenalezen")
    conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()


@router.patch("/{item_id}", response_model=ItemOut)
def update_item(item_id: int, body: ItemCreate):
    conn = get_conn()
    if not conn.execute("SELECT id FROM items WHERE id = ?", (item_id,)).fetchone():
        conn.close()
        raise HTTPException(404, "Item nenalezen")
    conn.execute(
        "UPDATE items SET name=?, unit=?, category=? WHERE id=?",
        (body.name, body.unit, body.category, item_id),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    conn.close()
    return _row_to_item(row)
