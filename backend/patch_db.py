"""Spusť pro inicializaci DB se všemi obchody."""
import sys
sys.path.insert(0, '.')
from app.database import init_db, get_conn

init_db()
conn = get_conn()
# Povol rohlik a kosik by default (mají nejlepší pokrytí), ostatní volitelně
conn.execute("UPDATE stores SET enabled = 1 WHERE id IN ('rohlik','kosik','kaufland','lidl','albert','billa','penny','globus','tesco')")
# Přidej logo a oprav barvy
updates = [
    ('rohlik',   '#ee4011', 'R'),
    ('kosik',    '#6db33f', 'K'),
    ('kaufland', '#e30613', 'Ka'),
    ('albert',   '#e2001a', 'Al'),
    ('billa',    '#ffcd00', 'Bi'),
    ('lidl',     '#0050aa', 'L'),
    ('penny',    '#c8102e', 'Pe'),
    ('globus',   '#009036', 'G'),
    ('tesco',    '#00539f', 'T'),
]
for store_id, color, logo in updates:
    conn.execute("UPDATE stores SET color=?, logo=? WHERE id=?", (color, logo, store_id))
conn.commit()
conn.close()
print("DB OK")
