# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**CenaHlídač** is a Czech grocery price tracker. It scrapes prices from 9 online supermarkets (Rohlík, Košík, Kaufland, Lidl, Albert, Billa, Penny, Globus, Tesco) and exposes a REST API for comparing prices and viewing history.

**Deployment model:** RPi runs the scraper + FastAPI backend. After each scrape, prices are exported as static JSON files and pushed to GitHub. GitHub Pages serves the read-only frontend directly from those JSON files — no always-on server needed for the public site.

## Commands

### Backend setup and run

```powershell
cd backend
pip install -r requirements.txt
playwright install chromium          # required for browser-based scrapers
python patch_db.py                   # one-time DB seed (stores + example items)
python -m uvicorn app.main:app --reload   # dev server at http://localhost:8000
python scheduler.py                  # standalone 6-hour refresh loop + auto git push
```

### Run frontend locally (PC)

```powershell
# Terminal 1 — FastAPI backend
cd backend
python -m uvicorn app.main:app --reload

# Terminal 2 — static file server from repo root
python -m http.server 3000
# Open: http://localhost:3000
```

### Manual export + push

```powershell
cd backend
python export_json.py               # export SQLite → ../data/*.json
# then from repo root:
git add data/ && git commit -m "data: manual export" && git push
```

### Trigger a manual scrape

```powershell
# Refresh prices for a single item (item_id = integer)
Invoke-RestMethod -Uri http://localhost:8000/api/prices/refresh/1 -Method Post

# Refresh all items in the background
Invoke-RestMethod -Uri http://localhost:8000/api/prices/refresh-all -Method Post
```

There is no test suite or linter configured.

## Architecture

### Data flow

1. **Scraper / scheduler** (`backend/scheduler.py`) — every 6 hours: scrapes all items, then calls `export_json.py` and `git push`.
2. **FastAPI** (`backend/app/main.py`) — three routers: `items`, `prices`, `stores`. SQLite database in WAL mode.
3. **Scrapers** (`backend/app/scrapers/`) — one file per store. Each exports `async search_product(query: str) -> dict | None`.
4. **Dispatcher** (`backend/app/scrapers/dispatcher.py`) — runs stores **serially** with `asyncio.sleep` delays to avoid Playwright event-loop conflicts.
5. **Database** (`backend/app/database.py`) — SQLite3, tables: `items`, `stores`, `price_history`. DB lives at `backend/data/prices.db` (gitignored).
6. **Export** (`backend/export_json.py`) — reads SQLite, writes static JSON to `data/` at repo root (committed to git).
7. **Frontend** (`price-tracker.jsx` + `index.html`) — Babel standalone + CDN React, no build step. Dual-mode: local vs. static.

### Frontend dual mode

`price-tracker.jsx` detects the environment via `window.location.hostname`:

| Mode | Condition | Data source | Features |
|------|-----------|-------------|----------|
| **Local** | `localhost` / `127.0.0.1` | `http://localhost:8000/api/*` | Add/remove items, manual refresh per item or all |
| **Static** | any other hostname (GitHub Pages) | `/data/*.json` | Read-only, shows last-updated timestamp |

### Static JSON files (repo root `data/`)

| File | Contents |
|------|----------|
| `data/meta.json` | `{ "last_updated": "2026-05-21T10:00:00Z" }` |
| `data/stores.json` | `{ "stores": [...] }` |
| `data/items.json` | `{ "items": [{ id, name, unit, category, prices: { store_id: { price, orig_price, on_sale, product_name, url, fetched_at } } }] }` |
| `data/history/{id}.json` | `{ "history": [{ store_id, price, orig_price, on_sale, fetched_at }] }` — last 30 days |

### Scraper strategy (per store)

Each scraper tries fast paths first and falls back to Playwright:

1. **JSON API / JSON-LD** — parse `<script type="application/ld+json">` or a JSON endpoint (faster, no browser needed).
2. **Playwright DOM** — launches headless Chromium with Czech locale, custom User-Agent, and `navigator.webdriver` override. Cookie banners are dismissed by `dismiss_cookies()` in `base.py`.

Price strings use Czech format (`"32,90 Kč"`); `parse_price()` in `base.py` normalises them to `float`.

### Key API surface

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/items` | List items |
| POST | `/api/items` | Create item (`name`, `unit`, `category`, `query`) |
| GET | `/api/items/{id}` | Item + current prices from all enabled stores |
| POST | `/api/prices/refresh/{id}` | Synchronous single-item scrape |
| POST | `/api/prices/refresh-all` | Background full refresh |
| GET | `/api/prices/history/{id}` | 30-day history, optional `?store_id=` filter |
| GET | `/api/prices/summary/basket` | Cheapest store per basket total |
| GET | `/api/stores` | List stores with enabled flag |
| PATCH | `/api/stores/{id}/toggle` | Enable/disable a store |

### GitHub Pages setup (one-time)

1. Push repo to GitHub.
2. Settings → Pages → Branch: `main`, folder: `/` (root).
3. Add `backend/data/` to `.gitignore` (SQLite DB must not be committed).
4. The `data/` folder at repo root IS committed — it holds the exported JSON.

## Important constraints

- **Serial scraping only** — do not switch `dispatcher.py` to `asyncio.gather`; Playwright contexts crash when shared across concurrent tasks.
- **Rate limiting via sleep** — 1.5 s between stores, 2 s between items; do not remove without adding a proper rate limiter.
- **No auth** — CORS is wide open (`allow_origins=["*"]`); this is intentional for local use.
- **Czech locale in Playwright** — `make_context()` sets `locale="cs-CZ"` and `Accept-Language: cs-CZ,cs`; changing this can break price extraction.
- **`orig_price` field** — presence of `orig_price > price` signals a sale; preserve this distinction when modifying scrapers.
- **`export_json.py` paths** — uses `__file__`-relative paths, so it works regardless of working directory. DB: `backend/data/prices.db`, export target: `data/` at repo root.
- **No build step** — `price-tracker.jsx` uses Babel standalone loaded from CDN. Do not add a bundler or npm build without discussing first.
