from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class ItemCreate(BaseModel):
    name: str
    unit: str = "1 ks"
    category: str = "Ostatní"
    query: str  # search term pro scraping


class ItemOut(BaseModel):
    id: int
    name: str
    unit: str
    category: str
    query: str
    created_at: str


class PriceEntry(BaseModel):
    store_id: str
    store_name: str
    price: float
    orig_price: Optional[float] = None
    on_sale: bool = False
    product_name: Optional[str] = None
    url: Optional[str] = None
    fetched_at: str


class ItemWithPrices(BaseModel):
    item: ItemOut
    prices: list[PriceEntry]
    cheapest_store: Optional[str] = None
    cheapest_price: Optional[float] = None


class StoreOut(BaseModel):
    id: str
    name: str
    color: str
    logo: str
    enabled: bool


class RefreshResult(BaseModel):
    item_id: int
    item_name: str
    scraped: int
    errors: list[str]
