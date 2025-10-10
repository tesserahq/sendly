from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID
from fastapi_pagination import Page, Params
from fastapi_pagination.ext.sqlalchemy import paginate

from app.db import get_db
from app.schemas.tenant import Tenant, TenantCreate, TenantUpdate
from app.services.tenant_service import TenantService

router = APIRouter(
    prefix="/tenants",
    tags=["tenants"],
    responses={404: {"description": "Not found"}},
)


@router.post("", response_model=Tenant, status_code=status.HTTP_201_CREATED)
def create_tenant(tenant: TenantCreate, db: Session = Depends(get_db)):
    """Create a new tenant."""
    tenant_service = TenantService(db)

    # Check if tenant name already exists
    if tenant_service.get_tenant_by_name(tenant.name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant with this name already exists",
        )

    return tenant_service.create_tenant(tenant)


@router.get("", response_model=Page[Tenant])
def list_tenants(
    db: Session = Depends(get_db),
    params: Params = Depends(),
):
    """List all tenants with pagination."""
    tenant_service = TenantService(db)
    query = tenant_service.get_tenants_query()
    return paginate(query, params)


@router.get("/{tenant_id}", response_model=Tenant)
def get_tenant(tenant_id: UUID, db: Session = Depends(get_db)):
    """Get a tenant by ID."""
    tenant = TenantService(db).get_tenant(tenant_id)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found"
        )
    return tenant


@router.put("/{tenant_id}", response_model=Tenant)
def update_tenant(tenant_id: UUID, tenant: TenantUpdate, db: Session = Depends(get_db)):
    """Update a tenant."""
    tenant_service = TenantService(db)

    # Check if tenant name is being updated and already exists
    if tenant.name:
        existing_tenant = tenant_service.get_tenant_by_name(tenant.name)
        if existing_tenant and existing_tenant.id != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Tenant with this name already exists",
            )

    updated_tenant = tenant_service.update_tenant(tenant_id, tenant)
    if not updated_tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found"
        )
    return updated_tenant


@router.delete("/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tenant(tenant_id: UUID, db: Session = Depends(get_db)):
    """Delete a tenant (soft delete)."""
    if not TenantService(db).delete_tenant(tenant_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found"
        )
