from fastapi import APIRouter, HTTPException
from app.database import get_conn
from app.schemas import ProductLinkCreate, ProductLinkOut

router = APIRouter()


@router.get("/{item_id}/links", response_model=list[ProductLinkOut])
def list_links(item_id: int):
    conn = get_conn()
    if not conn.execute("SELECT id FROM items WHERE id = ?", (item_id,)).fetchone():
        conn.close()
        raise HTTPException(404, "Item nenalezen")
    rows = conn.execute(
        "SELECT * FROM product_links WHERE item_id = ? ORDER BY store_id, id",
        (item_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.post("/{item_id}/links", response_model=ProductLinkOut, status_code=201)
def add_link(item_id: int, body: ProductLinkCreate):
    conn = get_conn()
    if not conn.execute("SELECT id FROM items WHERE id = ?", (item_id,)).fetchone():
        conn.close()
        raise HTTPException(404, "Item nenalezen")
    cur = conn.execute(
        "INSERT INTO product_links (item_id, store_id, url, label) VALUES (?,?,?,?)",
        (item_id, body.store_id, body.url, body.label),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM product_links WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return dict(row)


@router.delete("/links/{link_id}", status_code=204)
def delete_link(link_id: int):
    conn = get_conn()
    if not conn.execute("SELECT id FROM product_links WHERE id = ?", (link_id,)).fetchone():
        conn.close()
        raise HTTPException(404, "Odkaz nenalezen")
    conn.execute("DELETE FROM product_links WHERE id = ?", (link_id,))
    conn.commit()
    conn.close()
