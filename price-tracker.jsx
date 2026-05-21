const { useState, useEffect } = React;

// localhost → local mode (FastAPI backend), cokoliv jiného → static mode (GitHub Pages JSON)
const IS_STATIC = !(location.hostname === "localhost" || location.hostname === "127.0.0.1");
const API = "http://localhost:8000/api";

const STORE_META = {
  rohlik:   { name: "Rohlík",   color: "#ee4011", logo: "R" },
  kosik:    { name: "Košík",    color: "#6db33f", logo: "K" },
  kaufland: { name: "Kaufland", color: "#e30613", logo: "Ka" },
  lidl:     { name: "Lidl",     color: "#0050aa", logo: "L" },
  albert:   { name: "Albert",   color: "#e2001a", logo: "A" },
  billa:    { name: "Billa",    color: "#ffcd00", textColor: "#222", logo: "B" },
  penny:    { name: "Penny",    color: "#c8102e", logo: "P" },
  tesco:    { name: "Tesco",    color: "#00539f", logo: "T" },
  globus:   { name: "Globus",   color: "#009036", logo: "G" },
};

const CATEGORIES = ["Zelenina", "Ovoce", "Mléčné", "Maso", "Pečivo", "Trvanlivé", "Nápoje", "Ostatní"];

const smeta = (id) => STORE_META[id] || { name: id, color: "#555", logo: (id[0] || "?").toUpperCase() };
const fmtPrice = (p) => p != null ? `${(+p).toFixed(2)} Kč` : "—";
const savings = (orig, curr) => orig ? ((1 - curr / orig) * 100).toFixed(0) : 0;
const fmtDate = (d) => d
  ? new Date(d).toLocaleString("cs-CZ", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })
  : null;

// ── Data layer ─────────────────────────────────────────────────────────────

async function loadItems() {
  if (IS_STATIC) {
    const r = await fetch("data/items.json");
    return (await r.json()).items;
  }
  const list = await fetch(`${API}/items`).then(r => r.json());
  const details = await Promise.all(
    list.map(item => fetch(`${API}/items/${item.id}`).then(r => r.json()))
  );
  return details.map(({ item, prices }) => ({
    ...item,
    prices: Object.fromEntries(prices.map(p => [p.store_id, {
      price: p.price,
      orig_price: p.orig_price,
      on_sale: p.on_sale,
      product_name: p.product_name,
      url: p.url,
      fetched_at: p.fetched_at,
    }])),
  }));
}

async function loadHistory(itemId) {
  if (IS_STATIC) {
    const r = await fetch(`data/history/${itemId}.json`);
    return (await r.json()).history;
  }
  return fetch(`${API}/prices/history/${itemId}`).then(r => r.json());
}

async function loadMeta() {
  if (!IS_STATIC) return null;
  return fetch("data/meta.json")
    .then(r => r.json())
    .then(d => d.last_updated)
    .catch(() => null);
}

async function reloadItemPrices(itemId) {
  const detail = await fetch(`${API}/items/${itemId}`).then(r => r.json());
  return Object.fromEntries(detail.prices.map(p => [p.store_id, {
    price: p.price,
    orig_price: p.orig_price,
    on_sale: p.on_sale,
    product_name: p.product_name,
    url: p.url,
    fetched_at: p.fetched_at,
  }]));
}

// ── Sparkline ──────────────────────────────────────────────────────────────

function Sparkline({ history, storeId }) {
  const pts = history
    ? history.filter(h => !storeId || h.store_id === storeId).slice(-20).map(h => h.price)
    : [];

  if (pts.length < 2) {
    return (
      <svg viewBox="0 0 100 100" className="sparkline" preserveAspectRatio="none">
        <line x1="0" y1="50" x2="100" y2="50" stroke="var(--border)" strokeWidth="1.5" strokeDasharray="4,4" />
      </svg>
    );
  }

  const min = Math.min(...pts);
  const max = Math.max(...pts);
  const rng = max - min || 1;
  const norm = v => 90 - ((v - min) / rng) * 80;
  const coords = pts.map((v, i) => `${(i / (pts.length - 1)) * 100},${norm(v)}`);
  const last = coords[coords.length - 1].split(",");

  return (
    <svg viewBox="0 0 100 100" className="sparkline" preserveAspectRatio="none">
      <polyline
        points={coords.join(" ")}
        fill="none"
        stroke="var(--accent)"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx={last[0]} cy={last[1]} r="3" fill="var(--accent)" />
    </svg>
  );
}

// ── Store Badge ────────────────────────────────────────────────────────────

function StoreBadge({ storeId, small }) {
  const s = smeta(storeId);
  return (
    <span
      className={`store-badge ${small ? "store-badge--sm" : ""}`}
      style={{ background: s.color, color: s.textColor || "#fff" }}
    >
      {s.logo}
    </span>
  );
}

// ── Price Card ─────────────────────────────────────────────────────────────

function PriceCard({ item, history, onRemove, onRefresh }) {
  const [expanded, setExpanded] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const entries = Object.entries(item.prices || {})
    .filter(([, v]) => v.price != null)
    .sort((a, b) => a[1].price - b[1].price);

  const [cheapestId, cheapestData] = entries[0] || [null, null];
  const onSaleList = entries.filter(([, v]) => v.on_sale);

  const sparkHistory = history
    ? history.filter(h => !cheapestId || h.store_id === cheapestId)
    : null;

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await fetch(`${API}/prices/refresh/${item.id}`, { method: "POST" });
      await onRefresh(item.id);
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <div className={`card ${expanded ? "card--expanded" : ""}`}>
      <div className="card-header" onClick={() => setExpanded(e => !e)}>
        <div className="card-title-row">
          <div>
            <h3 className="card-name">{item.name}</h3>
            <span className="card-unit">{item.unit} · {item.category}</span>
          </div>
          {!IS_STATIC && (
            <div className="card-actions" onClick={e => e.stopPropagation()}>
              <button className={`btn-icon ${refreshing ? "spinning" : ""}`} onClick={handleRefresh} title="Aktualizovat">↻</button>
              <button className="btn-icon btn-icon--danger" onClick={() => onRemove(item.id)} title="Odebrat">×</button>
            </div>
          )}
        </div>

        {cheapestData ? (
          <div className="card-summary">
            <div className="best-price">
              <StoreBadge storeId={cheapestId} />
              <span className="price-main">{fmtPrice(cheapestData.price)}</span>
              <span className="price-label">nejlevněji</span>
            </div>
            {onSaleList.length > 0 && (
              <div className="sale-badges">
                {onSaleList.slice(0, 3).map(([sid, sv]) => (
                  <span key={sid} className="sale-chip">
                    <StoreBadge storeId={sid} small />
                    −{savings(sv.orig_price, sv.price)}%
                  </span>
                ))}
              </div>
            )}
            <div className="sparkline-wrap">
              <Sparkline history={sparkHistory} storeId={cheapestId} />
            </div>
          </div>
        ) : (
          <p className="no-data-label">Žádná data — spusť scraper</p>
        )}
      </div>

      {expanded && (
        <div className="card-body">
          {cheapestData?.fetched_at && (
            <p className="updated-label">Aktualizováno: {fmtDate(cheapestData.fetched_at)}</p>
          )}
          {entries.length === 0 ? (
            <p className="no-data-label" style={{ padding: "12px 0" }}>Žádné ceny</p>
          ) : (
            <div className="price-list">
              {entries.map(([sid, sv], i) => {
                const meta = smeta(sid);
                return (
                  <div key={sid} className={`price-row ${i === 0 ? "price-row--best" : ""} ${sv.on_sale ? "price-row--sale" : ""}`}>
                    <div className="price-row-left">
                      <StoreBadge storeId={sid} />
                      <div className="store-info">
                        <span className="store-name">{meta.name}</span>
                        {sv.product_name && <span className="product-name">{sv.product_name}</span>}
                      </div>
                    </div>
                    <div className="price-row-right">
                      {sv.on_sale && <span className="original-price">{fmtPrice(sv.orig_price)}</span>}
                      <span className="current-price">
                        {sv.url
                          ? <a href={sv.url} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()} style={{ color: "inherit", textDecoration: "none" }}>{fmtPrice(sv.price)}</a>
                          : fmtPrice(sv.price)
                        }
                      </span>
                      {sv.on_sale && <span className="sale-tag">SLEVA</span>}
                      {i === 0 && <span className="best-tag">✓</span>}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Add Item Modal ─────────────────────────────────────────────────────────

function AddModal({ onAdd, onClose }) {
  const [name, setName] = useState("");
  const [unit, setUnit] = useState("1 kg");
  const [category, setCategory] = useState(CATEGORIES[0]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async () => {
    if (!name.trim() || !query.trim()) return;
    setLoading(true);
    try {
      const res = await fetch(`${API}/items`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim(), unit, category, query: query.trim() }),
      });
      const newItem = await res.json();
      onAdd({ ...newItem, prices: {} });
      onClose();
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <h2 className="modal-title">Přidat surovinu</h2>
        <div className="form-group">
          <label>Název</label>
          <input value={name} onChange={e => setName(e.target.value)} placeholder="např. Špenát" autoFocus />
        </div>
        <div className="form-row">
          <div className="form-group">
            <label>Jednotka</label>
            <input value={unit} onChange={e => setUnit(e.target.value)} placeholder="1 kg" />
          </div>
          <div className="form-group">
            <label>Kategorie</label>
            <select value={category} onChange={e => setCategory(e.target.value)}>
              {CATEGORIES.map(c => <option key={c}>{c}</option>)}
            </select>
          </div>
        </div>
        <div className="form-group">
          <label>Hledaný výraz (pro scraper)</label>
          <input value={query} onChange={e => setQuery(e.target.value)} placeholder="např. špenát listový" />
        </div>
        <div className="modal-actions">
          <button className="btn btn--ghost" onClick={onClose}>Zrušit</button>
          <button className="btn btn--primary" onClick={handleSubmit} disabled={loading}>
            {loading ? "…" : "Přidat"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Summary Bar ────────────────────────────────────────────────────────────

function SummaryBar({ items }) {
  const storeIds = [...new Set(items.flatMap(item => Object.keys(item.prices || {})))];

  const totals = storeIds
    .map(sid => {
      const covered = items.filter(i => i.prices[sid]?.price != null);
      return {
        id: sid,
        meta: smeta(sid),
        total: covered.reduce((s, i) => s + i.prices[sid].price, 0),
        covered: covered.length,
        sales: covered.filter(i => i.prices[sid]?.on_sale).length,
      };
    })
    .filter(s => s.covered > 0)
    .sort((a, b) => a.total - b.total);

  if (totals.length === 0) {
    return (
      <div className="summary-bar">
        <p className="no-data-label">Žádná data pro srovnání — spusť scraper</p>
      </div>
    );
  }

  const best = totals[0];

  return (
    <div className="summary-bar">
      <div className="summary-highlight">
        <span className="summary-label">Nejlepší košík celkem</span>
        <div className="summary-best">
          <StoreBadge storeId={best.id} />
          <strong>{best.meta.name}</strong>
          <span className="summary-price">{fmtPrice(best.total)}</span>
          {best.sales > 0 && <span className="summary-sales">{best.sales} slev</span>}
          <span className="summary-sales" style={{ marginLeft: "auto" }}>{best.covered}/{items.length} položek</span>
        </div>
      </div>
      <div className="store-ranking">
        {totals.map((s, i) => (
          <div key={s.id} className="rank-row">
            <span className="rank-num">{i + 1}</span>
            <StoreBadge storeId={s.id} small />
            <span className="rank-name">{s.meta.name}</span>
            <span className="rank-price">{fmtPrice(s.total)}</span>
            <span className="rank-covered">{s.covered}/{items.length}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Main App ───────────────────────────────────────────────────────────────

function App() {
  const [items, setItems] = useState([]);
  const [historyCache, setHistoryCache] = useState({});
  const [lastUpdated, setLastUpdated] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [refreshStatus, setRefreshStatus] = useState(null);
  const [showModal, setShowModal] = useState(false);
  const [filter, setFilter] = useState("Vše");
  const [search, setSearch] = useState("");
  const [view, setView] = useState("items");

  useEffect(() => {
    Promise.all([loadItems(), loadMeta()])
      .then(([loadedItems, meta]) => {
        setItems(loadedItems);
        setLastUpdated(meta);
        // history se načítá na pozadí pro sparklines
        loadedItems.forEach(item => {
          loadHistory(item.id)
            .then(h => setHistoryCache(prev => ({ ...prev, [item.id]: h })))
            .catch(() => {});
        });
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const handleRemove = async (id) => {
    await fetch(`${API}/items/${id}`, { method: "DELETE" }).catch(() => {});
    setItems(prev => prev.filter(i => i.id !== id));
  };

  const handleAdd = (item) => setItems(prev => [...prev, item]);

  const handleRefreshItem = async (itemId) => {
    const newPrices = await reloadItemPrices(itemId);
    setItems(prev => prev.map(i => i.id === itemId ? { ...i, prices: newPrices } : i));
    loadHistory(itemId).then(h => setHistoryCache(prev => ({ ...prev, [itemId]: h }))).catch(() => {});
  };

  const handleRefreshAll = async () => {
    setRefreshStatus("Spouštím…");
    await fetch(`${API}/prices/refresh-all`, { method: "POST" }).catch(() => {});
    setRefreshStatus("Scraping běží na pozadí, výsledky se zobrazí po dokončení");
    setTimeout(() => setRefreshStatus(null), 8000);
  };

  const cats = ["Vše", ...CATEGORIES];
  const filtered = items.filter(i =>
    (filter === "Vše" || i.category === filter) &&
    i.name.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Mono:ital,wght@0,400;0,500;1,400&family=Syne:wght@600;700;800&display=swap');

        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

        :root {
          --bg: #0e0f13;
          --surface: #15171e;
          --surface2: #1c1e27;
          --border: #252730;
          --accent: #4fd1a5;
          --accent2: #f7c948;
          --danger: #e05252;
          --text: #e8e9ef;
          --muted: #6b6e7e;
          --radius: 12px;
        }

        body { background: var(--bg); color: var(--text); font-family: 'DM Mono', monospace; min-height: 100vh; }

        .app { max-width: 960px; margin: 0 auto; padding: 24px 16px 80px; }

        /* Header */
        .header { margin-bottom: 32px; }
        .header-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; flex-wrap: wrap; }
        .brand { display: flex; flex-direction: column; gap: 2px; }
        .brand-title {
          font-family: 'Syne', sans-serif; font-weight: 800;
          font-size: clamp(22px, 5vw, 32px); letter-spacing: -0.03em;
          background: linear-gradient(120deg, var(--accent), #7ee8c8, var(--accent2));
          -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
        }
        .brand-sub { font-size: 11px; color: var(--muted); letter-spacing: 0.08em; text-transform: uppercase; }
        .header-actions { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
        .refresh-status { font-size: 11px; color: var(--accent2); }

        /* Tabs */
        .tabs { display: flex; gap: 2px; background: var(--surface); border-radius: 8px; padding: 3px; margin-bottom: 20px; width: fit-content; }
        .tab { padding: 6px 16px; border-radius: 6px; border: none; background: none; color: var(--muted); font-family: inherit; font-size: 13px; cursor: pointer; transition: all 0.15s; }
        .tab.active { background: var(--surface2); color: var(--text); }

        /* Filters */
        .filters { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; margin-bottom: 20px; }
        .search-input { flex: 1; min-width: 180px; background: var(--surface); border: 1px solid var(--border); color: var(--text); border-radius: 8px; padding: 8px 14px; font-family: inherit; font-size: 13px; outline: none; transition: border-color 0.15s; }
        .search-input:focus { border-color: var(--accent); }
        .search-input::placeholder { color: var(--muted); }
        .cat-pills { display: flex; gap: 6px; flex-wrap: wrap; }
        .cat-pill { padding: 5px 12px; border-radius: 20px; border: 1px solid var(--border); background: none; color: var(--muted); font-family: inherit; font-size: 12px; cursor: pointer; transition: all 0.15s; }
        .cat-pill.active { background: var(--accent); border-color: var(--accent); color: #0a1a14; font-weight: 600; }

        /* Cards */
        .cards-grid { display: grid; gap: 12px; }
        .card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; transition: border-color 0.2s; }
        .card:hover { border-color: #333640; }
        .card--expanded { border-color: var(--accent); }
        .card-header { padding: 16px; cursor: pointer; }
        .card-title-row { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px; }
        .card-name { font-family: 'Syne', sans-serif; font-size: 17px; font-weight: 700; letter-spacing: -0.01em; }
        .card-unit { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.06em; }
        .card-actions { display: flex; gap: 4px; }
        .card-summary { display: flex; gap: 16px; align-items: center; flex-wrap: wrap; }
        .best-price { display: flex; align-items: center; gap: 8px; }
        .price-main { font-size: 22px; font-weight: 500; color: var(--accent); letter-spacing: -0.02em; }
        .price-label { font-size: 11px; color: var(--muted); }
        .sale-badges { display: flex; gap: 5px; flex-wrap: wrap; }
        .sale-chip { display: flex; align-items: center; gap: 4px; background: rgba(247,201,72,0.12); border: 1px solid rgba(247,201,72,0.3); color: var(--accent2); border-radius: 6px; padding: 3px 8px; font-size: 11px; font-weight: 600; }
        .sparkline-wrap { margin-left: auto; width: 90px; height: 36px; opacity: 0.7; }
        .sparkline { width: 100%; height: 100%; }

        /* Card body */
        .card-body { padding: 0 16px 16px; border-top: 1px solid var(--border); }
        .updated-label { font-size: 10px; color: var(--muted); text-align: right; margin: 10px 0 8px; letter-spacing: 0.04em; }
        .price-list { display: flex; flex-direction: column; gap: 4px; }
        .price-row { display: flex; justify-content: space-between; align-items: center; padding: 8px 10px; border-radius: 8px; background: var(--surface2); border: 1px solid transparent; transition: all 0.1s; }
        .price-row--best { border-color: rgba(79,209,165,0.2); background: rgba(79,209,165,0.05); }
        .price-row--sale { background: rgba(247,201,72,0.04); }
        .price-row-left { display: flex; align-items: center; gap: 10px; min-width: 0; }
        .store-info { display: flex; flex-direction: column; min-width: 0; }
        .store-name { font-size: 13px; }
        .product-name { font-size: 10px; color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 220px; }
        .price-row-right { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
        .original-price { font-size: 12px; color: var(--muted); text-decoration: line-through; }
        .current-price { font-size: 15px; font-weight: 500; }
        .sale-tag { font-size: 9px; font-weight: 700; background: var(--accent2); color: #1a1200; padding: 2px 6px; border-radius: 4px; letter-spacing: 0.06em; }
        .best-tag { font-size: 13px; color: var(--accent); }
        .no-data-label { font-size: 12px; color: var(--muted); margin-top: 6px; }

        /* Store badges */
        .store-badge { display: inline-flex; align-items: center; justify-content: center; width: 26px; height: 26px; border-radius: 6px; font-family: 'Syne', sans-serif; font-weight: 800; font-size: 11px; flex-shrink: 0; }
        .store-badge--sm { width: 16px; height: 16px; border-radius: 4px; font-size: 8px; }

        /* Buttons */
        .btn { padding: 9px 18px; border-radius: 8px; border: none; font-family: inherit; font-size: 13px; cursor: pointer; transition: all 0.15s; font-weight: 500; }
        .btn--primary { background: var(--accent); color: #0a1a14; }
        .btn--primary:hover { filter: brightness(1.1); }
        .btn--ghost { background: var(--surface); border: 1px solid var(--border); color: var(--text); }
        .btn--ghost:hover { border-color: #444; }
        .btn-icon { width: 30px; height: 30px; border-radius: 7px; border: 1px solid var(--border); background: var(--surface2); color: var(--muted); font-size: 16px; display: flex; align-items: center; justify-content: center; cursor: pointer; transition: all 0.15s; font-family: inherit; }
        .btn-icon:hover { color: var(--text); border-color: #444; }
        .btn-icon--danger:hover { color: var(--danger); border-color: var(--danger); }
        .btn-refresh { display: flex; align-items: center; gap: 6px; }
        @keyframes spin { to { transform: rotate(360deg); } }
        .spinning { animation: spin 0.6s linear infinite; }

        /* Modal */
        .modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.7); backdrop-filter: blur(4px); display: flex; align-items: center; justify-content: center; z-index: 100; padding: 16px; }
        .modal { background: var(--surface); border: 1px solid var(--border); border-radius: 16px; padding: 28px; width: 100%; max-width: 420px; }
        .modal-title { font-family: 'Syne', sans-serif; font-size: 20px; font-weight: 700; margin-bottom: 20px; }
        .form-group { display: flex; flex-direction: column; gap: 6px; margin-bottom: 14px; }
        .form-group label { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.07em; }
        .form-group input, .form-group select { background: var(--surface2); border: 1px solid var(--border); color: var(--text); border-radius: 8px; padding: 9px 12px; font-family: inherit; font-size: 14px; outline: none; transition: border-color 0.15s; }
        .form-group input:focus, .form-group select:focus { border-color: var(--accent); }
        .form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
        .modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 20px; }

        /* Summary */
        .summary-bar { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; }
        .summary-label { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.07em; display: block; margin-bottom: 10px; }
        .summary-best { display: flex; align-items: center; gap: 12px; padding: 14px; background: rgba(79,209,165,0.08); border: 1px solid rgba(79,209,165,0.2); border-radius: 10px; margin-bottom: 20px; }
        .summary-best strong { font-family: 'Syne', sans-serif; font-size: 16px; }
        .summary-price { font-size: 20px; color: var(--accent); font-weight: 500; }
        .summary-sales { font-size: 11px; background: rgba(247,201,72,0.15); color: var(--accent2); padding: 3px 8px; border-radius: 10px; }
        .store-ranking { display: flex; flex-direction: column; gap: 6px; }
        .rank-row { display: flex; align-items: center; gap: 10px; padding: 8px 10px; border-radius: 8px; background: var(--surface2); }
        .rank-num { font-size: 12px; color: var(--muted); width: 16px; text-align: center; }
        .rank-name { font-size: 13px; flex: 1; }
        .rank-price { font-size: 14px; font-weight: 500; }
        .rank-covered { font-size: 11px; color: var(--muted); }

        /* States */
        .loading-state { display: flex; align-items: center; justify-content: center; height: 60vh; color: var(--muted); font-size: 14px; }
        .error-state { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 60vh; gap: 8px; text-align: center; }
        .error-state p { color: var(--danger); font-size: 16px; }
        .error-state small { color: var(--muted); font-size: 12px; }
        .empty { text-align: center; padding: 60px 20px; color: var(--muted); }
        .empty-icon { font-size: 40px; margin-bottom: 12px; }
        .empty p { font-size: 14px; line-height: 1.6; }

        /* Scrollbar */
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-track { background: var(--bg); }
        ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
      `}</style>

      <div className="app">
        {loading ? (
          <div className="loading-state">Načítám data…</div>
        ) : error ? (
          <div className="error-state">
            <p>Chyba při načítání</p>
            <small>{error}</small>
            {!IS_STATIC && <small>Běží backend na http://localhost:8000?</small>}
          </div>
        ) : (
          <>
            <header className="header">
              <div className="header-top">
                <div className="brand">
                  <h1 className="brand-title">CenaHlídač</h1>
                  <span className="brand-sub">
                    {IS_STATIC && lastUpdated
                      ? `Aktualizováno ${fmtDate(lastUpdated)}`
                      : "Tracker cen potravin"}
                  </span>
                </div>
                {!IS_STATIC && (
                  <div className="header-actions">
                    {refreshStatus && <span className="refresh-status">{refreshStatus}</span>}
                    <button className="btn btn--ghost btn-refresh" onClick={handleRefreshAll}>
                      ↻ Aktualizovat vše
                    </button>
                    <button className="btn btn--primary" onClick={() => setShowModal(true)}>
                      + Přidat surovinu
                    </button>
                  </div>
                )}
              </div>
            </header>

            <div className="tabs">
              <button className={`tab ${view === "items" ? "active" : ""}`} onClick={() => setView("items")}>
                Suroviny ({items.length})
              </button>
              <button className={`tab ${view === "summary" ? "active" : ""}`} onClick={() => setView("summary")}>
                Srovnání košíku
              </button>
            </div>

            {view === "items" && (
              <>
                <div className="filters">
                  <input
                    className="search-input"
                    placeholder="Hledat surovinu…"
                    value={search}
                    onChange={e => setSearch(e.target.value)}
                  />
                  <div className="cat-pills">
                    {cats.map(c => (
                      <button
                        key={c}
                        className={`cat-pill ${filter === c ? "active" : ""}`}
                        onClick={() => setFilter(c)}
                      >
                        {c}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="cards-grid">
                  {filtered.length === 0 ? (
                    <div className="empty">
                      <div className="empty-icon">🛒</div>
                      <p>Žádné suroviny nenalezeny.<br />Zkus jiný filtr nebo přidej novou.</p>
                    </div>
                  ) : (
                    filtered.map(item => (
                      <PriceCard
                        key={item.id}
                        item={item}
                        history={historyCache[item.id] || null}
                        onRemove={handleRemove}
                        onRefresh={handleRefreshItem}
                      />
                    ))
                  )}
                </div>
              </>
            )}

            {view === "summary" && <SummaryBar items={items} />}
          </>
        )}
      </div>

      {showModal && !IS_STATIC && <AddModal onAdd={handleAdd} onClose={() => setShowModal(false)} />}
    </>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(React.createElement(App));
