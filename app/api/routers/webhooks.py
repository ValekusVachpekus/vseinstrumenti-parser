from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from app.api.deps import SessionDep, TenantDep
from app.api.schemas import WebhookCreate, WebhookOut
from app.db.models import WebhookEndpoint

router = APIRouter(prefix="/v1/webhooks", tags=["webhooks"])


@router.post("", response_model=WebhookOut, status_code=status.HTTP_201_CREATED)
async def create_webhook(payload: WebhookCreate, tenant: TenantDep, session: SessionDep):
    endpoint = WebhookEndpoint(
        tenant_id=tenant.id,
        url=payload.url,
        secret=payload.secret,
        event_types=payload.event_types,
    )
    session.add(endpoint)
    await session.commit()
    await session.refresh(endpoint)
    return endpoint


@router.get("", response_model=list[WebhookOut])
async def list_webhooks(tenant: TenantDep, session: SessionDep):
    stmt = select(WebhookEndpoint).where(WebhookEndpoint.tenant_id == tenant.id)
    return list((await session.execute(stmt)).scalars().all())


@router.delete("/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook(webhook_id: int, tenant: TenantDep, session: SessionDep):
    endpoint = await session.get(WebhookEndpoint, webhook_id)
    if endpoint is None or endpoint.tenant_id != tenant.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Webhook not found")
    await session.delete(endpoint)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
