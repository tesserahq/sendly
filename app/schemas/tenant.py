from pydantic import BaseModel
from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime


class TenantBase(BaseModel):
    """Base tenant model containing common tenant attributes."""

    name: str
    """Tenant name. Required field."""

    provider_id: UUID
    """Provider ID. Required field."""

    provider_settings: Dict[str, Any]
    """Provider API key. Required field."""


class TenantCreate(TenantBase):
    """Schema for creating a new tenant. Inherits all fields from TenantBase."""

    pass


class TenantUpdate(BaseModel):
    """Schema for updating an existing tenant. All fields are optional."""

    name: Optional[str] = None
    """Updated tenant name."""

    provider_id: Optional[UUID] = None
    """Updated provider ID."""

    provider_settings: Optional[Dict[str, Any]] = None
    """Updated provider settings."""


class TenantInDB(TenantBase):
    """Schema representing a tenant as stored in the database. Includes database-specific fields."""

    id: UUID
    """Unique identifier for the tenant in the database."""

    created_at: datetime
    """Timestamp when the tenant record was created."""

    updated_at: datetime
    """Timestamp when the tenant record was last updated."""

    model_config = {"from_attributes": True}


class Tenant(TenantInDB):
    """Schema for tenant data returned in API responses. Inherits all fields from TenantInDB."""

    pass
