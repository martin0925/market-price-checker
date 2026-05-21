"""
Exportuje data z SQLite do JSON souborů pro GitHub Pages.
Spuštění: python export_json.py  (z backend/ adresáře)
"""

import json
import os
import sqlite3
from datetime import datetime, timezone

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("DB_PATH", os.path.join(_SCRIPT_DIR, "data", "prices.db"))
EXPORT_DIR = os.environ.get("EXPORT_DIR", os.path.join(_SCRIPT_DIR, "..", "data"))


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def _write(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))


def export():
    os.makedirs(EXPORT_DIR, exist_ok=True)
    os.makedirs(os.path.join(EXPORT_DIR, "history"), exist_ok=True)

    conn = _conn()

    # stores.json
    stores = [dict(r) for r in conn.execute(
        "SELECT id, name, color, logo, enabled FROM stores ORDER BY name"
    ).fetchall()]
    for s in stores:
        s["enabled"] = bool(s["enabled"])
    _write(os.path.join(EXPORT_DIR, "stores.json"), {"stores": stores})

    # items.json — každý item s nejnovější cenou per store
    item_rows = conn.execute("SELECT * FROM items ORDER BY name").fetchall()
    items = []
    for item in item_rows:
        iid = item["id"]
        price_rows = conn.execute("""
            SELECT ph.store_id, ph.price, ph.orig_price, ph.product_name, ph.url, ph.fetched_at
            FROM price_history ph
            WHERE ph.item_id = ?
              AND ph.fetched_at = (
                SELECT MAX(ph2.fetched_at) FROM price_history ph2
                WHERE ph2.item_id = ph.item_id AND ph2.store_id = ph.store_id
              )
            ORDER BY ph.price ASC
        """, (iid,)).fetchall()

        prices = {}
        for r in price_rows:
            prices[r["store_id"]] = {
                "price": r["price"],
                "orig_price": r["orig_price"],
                "on_sale": r["orig_price"] is not None,
                "product_name": r["product_name"],
                "url": r["url"],
                "fetched_at": r["fetched_at"],
            }

        items.append({
            "id": iid,
            "name": item["name"],
            "unit": item["unit"],
            "category": item["category"],
            "prices": prices,
        })

    _write(os.path.join(EXPORT_DIR, "items.json"), {"items": items})

    # history/{id}.json — 30denní historie per item
    for item in item_rows:
        iid = item["id"]
        rows = conn.execute("""
            SELECT ph.store_id, s.name AS store_name, ph.price, ph.orig_price, ph.fetched_at
            FROM price_history ph
            JOIN stores s ON s.id = ph.store_id
            WHERE ph.item_id = ?
              AND ph.fetched_at >= datetime('now', '-30 days')
            ORDER BY ph.fetched_at DESC
        """, (iid,)).fetchall()

        _write(
            os.path.join(EXPORT_DIR, "history", f"{iid}.json"),
            {"history": [dict(r) for r in rows]},
        )

    conn.close()

    # meta.json
    _write(os.path.join(EXPORT_DIR, "meta.json"), {
        "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    })

    print(f"✅ Exportováno {len(items)} itemů do {os.path.abspath(EXPORT_DIR)}")


if __name__ == "__main__":
    export()
