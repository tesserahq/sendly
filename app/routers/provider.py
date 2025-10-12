from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID
from fastapi_pagination import Page, Params
from fastapi_pagination.ext.sqlalchemy import paginate

from app.db import get_db
from app.schemas.provider import Provider, ProviderCreate, ProviderUpdate
from app.services.provider_service import ProviderService
from app.models.provider import Provider as ProviderModel

router = APIRouter(
    prefix="/providers",
    tags=["providers"],
    responses={404: {"description": "Not found"}},
)


@router.post("", response_model=Provider, status_code=status.HTTP_201_CREATED)
def create_provider(provider: ProviderCreate, db: Session = Depends(get_db)):
    """Create a new provider."""
    provider_service = ProviderService(db)

    # Check if provider name already exists
    if provider_service.get_provider_by_name(provider.name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provider with this name already exists",
        )

    return provider_service.create_provider(provider)


@router.get("", response_model=Page[Provider])
def list_providers(
    db: Session = Depends(get_db),
    params: Params = Depends(),
):
    """List all providers with pagination."""
    query = db.query(ProviderModel).order_by(ProviderModel.created_at.desc())
    return paginate(query, params)


@router.get("/{provider_id}", response_model=Provider)
def get_provider(provider_id: UUID, db: Session = Depends(get_db)):
    """Get a provider by ID."""
    provider = ProviderService(db).get_provider(provider_id)
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found"
        )
    return provider


@router.put("/{provider_id}", response_model=Provider)
def update_provider(
    provider_id: UUID, provider: ProviderUpdate, db: Session = Depends(get_db)
):
    """Update a provider."""
    provider_service = ProviderService(db)

    # Check if provider name is being updated and already exists
    if provider.name:
        existing_provider = provider_service.get_provider_by_name(provider.name)
        if existing_provider and existing_provider.id != provider_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Provider with this name already exists",
            )

    updated_provider = provider_service.update_provider(provider_id, provider)
    if not updated_provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found"
        )
    return updated_provider


@router.delete("/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_provider(provider_id: UUID, db: Session = Depends(get_db)):
    """Delete a provider (soft delete)."""
    if not ProviderService(db).delete_provider(provider_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found"
        )
