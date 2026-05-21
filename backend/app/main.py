from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.database import init_db
from app.routers import items, prices, stores


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="CenaHlídač API",
    description="Tracker cen potravin napříč českými supermarkety",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(items.router, prefix="/api/items", tags=["items"])
app.include_router(prices.router, prefix="/api/prices", tags=["prices"])
app.include_router(stores.router, prefix="/api/stores", tags=["stores"])


@app.get("/")
def root():
    return {"status": "ok", "message": "CenaHlídač API běží"}
