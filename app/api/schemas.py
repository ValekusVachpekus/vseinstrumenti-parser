from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ProductCreate(BaseModel):
    # Full product URL or a bare numeric product id.
    ref: str = Field(..., description="Product URL or numeric vi_product_id")
    check_interval_seconds: int | None = Field(default=None, ge=60)


class ProductUpdate(BaseModel):
    check_interval_seconds: int | None = Field(default=None, ge=60)
    is_active: bool | None = None


class SnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    captured_at: datetime
    price: Decimal | None
    old_price: Decimal | None
    discount_pct: Decimal | None
    in_stock: bool | None
    availability_raw: str | None
    promo_labels: list[str] | None


class CrawlLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    http_status: int | None
    started_at: datetime
    finished_at: datetime | None
    error: str | None


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    vi_product_id: str
    url: str
    slug: str | None
    title: str | None
    city: str | None
    check_interval_seconds: int | None
    is_active: bool
    next_check_at: datetime | None
    last_checked_at: datetime | None
    created_at: datetime


class ProductDetail(ProductOut):
    current: SnapshotOut | None = None


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    type: str
    old_value: str | None
    new_value: str | None
    payload: dict | None
    created_at: datetime


class PricePoint(BaseModel):
    captured_at: datetime
    price: Decimal | None
    old_price: Decimal | None
    discount_pct: Decimal | None
    in_stock: bool | None


class CheckResponse(BaseModel):
    job_id: str | None
    product_id: int


class BulkCheckRequest(BaseModel):
    product_ids: list[int] | None = Field(
        default=None, description="If omitted, checks all active products of the tenant."
    )


class BulkCheckResponse(BaseModel):
    enqueued: int
    job_ids: list[str]


class JobOut(BaseModel):
    job_id: str
    status: str
    result: dict | None = None


class WebhookCreate(BaseModel):
    url: str
    secret: str | None = None
    event_types: list[str] | None = None


class WebhookOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    url: str
    event_types: list[str] | None
    is_active: bool
    created_at: datetime


class Page(BaseModel):
    total: int
    limit: int
    offset: int
