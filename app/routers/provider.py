"""API routes for listing email providers."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.providers.registry import list_providers
from app.schemas.common import ListResponse
from app.schemas.provider import ProviderRead

router = APIRouter(
    prefix="/providers",
    tags=["providers"],
    responses={404: {"description": "Not found"}},
)


@router.get("/", response_model=ListResponse[ProviderRead])
def list_email_providers(
    enabled_only: bool = Query(
        False, description="If true, return only enabled providers"
    ),
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
