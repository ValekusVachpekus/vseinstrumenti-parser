from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import make_asgi_app

from app.api.routers import events, health, jobs, products, webhooks
from app.core.logging import configure_logging

configure_logging()

app = FastAPI(
    title="VI Monitor API",
    version="0.1.0",
    description="Monitoring of vseinstrumenti.ru product cards: price, availability, discounts, promos.",
)

# Permissive CORS for the local test UI.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(products.router)
app.include_router(events.router)
app.include_router(jobs.router)
app.include_router(webhooks.router)

# Prometheus metrics endpoint.
app.mount("/metrics", make_asgi_app())

# Test UI (static single-page app).
_WEB_DIR = Path(__file__).resolve().parents[2] / "web"
if _WEB_DIR.is_dir():
    app.mount("/ui", StaticFiles(directory=str(_WEB_DIR), html=True), name="ui")

    @app.get("/", include_in_schema=False)
    async def _root() -> RedirectResponse:
        return RedirectResponse(url="/ui/")
