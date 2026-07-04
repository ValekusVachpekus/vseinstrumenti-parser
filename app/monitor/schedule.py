from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.db.models import Product


def interval_for(product: Product) -> int:
    return product.check_interval_seconds or settings.default_check_interval_seconds


def compute_next_check_at(product: Product, now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    jitter = random.randint(0, max(settings.schedule_jitter_seconds, 0))
    return now + timedelta(seconds=interval_for(product) + jitter)
