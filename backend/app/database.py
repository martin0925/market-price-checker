import sqlite3
import os

DB_PATH = os.environ.get("DB_PATH", "data/prices.db")


def get_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS items (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            name      TEXT NOT NULL,
            unit      TEXT NOT NULL DEFAULT '1 ks',
            category  TEXT NOT NULL DEFAULT 'Ostatní',
            query     TEXT NOT NULL DEFAULT '', -- legacy, nahrazeno product_links
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS stores (
            id      TEXT PRIMARY KEY,         -- 'rohlik', 'kosik', ...
            name    TEXT NOT NULL,
            color   TEXT NOT NULL,
            logo    TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS product_links (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id    INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
            store_id   TEXT    NOT NULL REFERENCES stores(id),
            url        TEXT    NOT NULL,
            label      TEXT    NOT NULL DEFAULT '',
            active     INTEGER NOT NULL DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_pl_item ON product_links(item_id);

        CREATE TABLE IF NOT EXISTS price_history (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id    INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
            store_id   TEXT    NOT NULL REFERENCES stores(id),
            price      REAL    NOT NULL,
            orig_price REAL,                  -- NULL pokud není sleva
            product_name TEXT,               -- přesný název produktu na daném e-shopu
            url        TEXT,
            fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_ph_item_store
            ON price_history(item_id, store_id, fetched_at DESC);

        -- Seed stores
        INSERT OR IGNORE INTO stores VALUES
            ('rohlik', 'Rohlík',   '#ee4011', 'R', 1),
            ('kosik',  'Košík',    '#6db33f', 'K', 1),
            ('kaufland','Kaufland','#e30613', 'Ka', 0),
            ('lidl',   'Lidl',     '#0050aa', 'L', 0),
            ('albert', 'Albert',   '#e2001a', 'A', 0),
            ('billa',  'Billa',    '#ffcd00', 'B', 0),
            ('penny',  'Penny',    '#c8102e', 'P', 0),
            ('tesco',  'Tesco',    '#00539f', 'T', 0),
            ('globus', 'Globus',   '#009036', 'G', 0);

        -- Seed example items
        INSERT OR IGNORE INTO items(name, unit, category, query) VALUES
            ('Brambory',          '1 kg',   'Zelenina',  'brambory'),
            ('Mléko plnotučné',   '1 l',    'Mléčné',    'mléko plnotučné'),
            ('Chleba kmínový',    '500 g',  'Pečivo',    'chleba kmínový'),
            ('Kuřecí prsa',       '1 kg',   'Maso',      'kuřecí prsa'),
            ('Máslo',             '250 g',  'Mléčné',    'máslo'),
            ('Banány',            '1 kg',   'Ovoce',     'banány'),
            ('Vejce',             '10 ks',  'Mléčné',    'vejce 10'),
            ('Rýže dlouhozrnná',  '1 kg',   'Trvanlivé', 'rýže dlouhozrnná'),
            ('Olivový olej',      '500 ml', 'Trvanlivé', 'olivový olej');
    """)
    conn.commit()
    conn.close()
    print("✅ DB inicializována")
