from fastapi import APIRouter, HTTPException
from app.database import get_conn
from app.schemas import StoreOut

router = APIRouter()


@router.get("/", response_model=list[StoreOut])
def list_stores():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM stores ORDER BY name").fetchall()
    conn.close()
    return [StoreOut(id=r["id"], name=r["name"], color=r["color"],
                     logo=r["logo"], enabled=bool(r["enabled"])) for r in rows]


@router.patch("/{store_id}/toggle", response_model=StoreOut)
def toggle_store(store_id: str):
    conn = get_conn()
    row = conn.execute("SELECT * FROM stores WHERE id = ?", (store_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Obchod nenalezen")
    new_val = 0 if row["enabled"] else 1
    conn.execute("UPDATE stores SET enabled = ? WHERE id = ?", (new_val, store_id))
    conn.commit()
    row = conn.execute("SELECT * FROM stores WHERE id = ?", (store_id,)).fetchone()
    conn.close()
    return StoreOut(id=row["id"], name=row["name"], color=row["color"],
                    logo=row["logo"], enabled=bool(row["enabled"]))
