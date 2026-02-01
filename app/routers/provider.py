"""API routes for listing email providers and handling delivery events."""

from __future__ import annotations

from typing import Dict, Any
from fastapi import APIRouter, Query, Request, HTTPException, Depends, status
from sqlalchemy.orm import Session

from app.providers.registry import list_providers, get_provider
from app.schemas.common import ListResponse
from app.schemas.provider import ProviderRead
from app.db import get_db
from app.commands.providers.process_delivery_events_command import (
    ProcessDeliveryEventsCommand,
)
from app.auth.rbac import build_rbac_dependencies

router = APIRouter(
    prefix="/providers",
    tags=["providers"],
    responses={404: {"description": "Not found"}},
)


async def infer_domain(_request: Request) -> str:
    """
    Infer the domain from the query parameter 'domain'.
    """
    return "*"


PROVIDER_RESOURCE = "provider"
rbac_providers = build_rbac_dependencies(
    resource=PROVIDER_RESOURCE,
    project_resolver=infer_domain,
)


PROVIDER_DELIVERY_EVENT_RESOURCE = "provider.delivery_event"
rbac_provider_delivery_events = build_rbac_dependencies(
    resource=PROVIDER_DELIVERY_EVENT_RESOURCE,
    project_resolver=infer_domain,
)


@router.get("/", response_model=ListResponse[ProviderRead])
def list_email_providers(
    enabled_only: bool = Query(
        False, description="If true, return only enabled providers"
    ),
    _authorized: bool = Depends(rbac_providers["read"]),
) -> ListResponse[ProviderRead]:
    """List registered email providers with their metadata (name, enabled, default, site)."""
    providers_map = list_providers(enabled_only=enabled_only)
    data = [
        ProviderRead(
            id=slug,
            name=config.name,
            enabled=config.enabled,
            default=config.default,
            site=config.site,
        )
        for slug, config in providers_map.items()
    ]
    return ListResponse(items=data)


@router.post(
    "/{provider_id}/delivery-events",
    status_code=status.HTTP_200_OK,
    response_model=Dict[str, Any],
)
async def receive_delivery_events(
    provider_id: str,
    request: Request,
    _authorized: bool = Depends(rbac_provider_delivery_events["create"]),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Receive and process email delivery events from provider webhooks.

    This endpoint accepts webhook callbacks from email providers (Postmark, SendGrid, etc.)
    and normalizes them into EmailEvent objects for storage and processing.

    Args:
        provider_id: The email provider identifier (e.g., 'postmark', 'sendgrid')
        request: The raw request containing webhook payload and headers
        db: Database session

    Returns:
        Dict with status and processed events count

    Raises:
        HTTPException: If provider not found or webhook verification fails
    """
    # Get the provider instance
    try:
        provider = get_provider(provider_id, settings={})
    except (KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider '{provider_id}' not found or not enabled",
        )

    # Read raw body and headers
    body_bytes = await request.body()
    headers = dict(request.headers)

    # Parse JSON payload
    try:
        payload = await request.json()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON payload: {str(e)}",
        )

    # Execute command to process events
    command = ProcessDeliveryEventsCommand(db)
    result = command.execute(provider, body_bytes, payload, headers)

    return result
