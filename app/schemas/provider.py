from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from datetime import datetime


class ProviderBase(BaseModel):
    """Base provider model containing common provider attributes."""

    name: str
    """Provider name. Required field."""


class ProviderCreate(ProviderBase):
    """Schema for creating a new provider. Inherits all fields from ProviderBase."""

    pass


class ProviderUpdate(BaseModel):
    """Schema for updating an existing provider. All fields are optional."""

    name: Optional[str] = None
    """Updated provider name."""


class ProviderInDB(ProviderBase):
    """Schema representing a provider as stored in the database. Includes database-specific fields."""

    id: UUID
    """Unique identifier for the provider in the database."""

    created_at: datetime
    """Timestamp when the provider record was created."""

    updated_at: datetime
    """Timestamp when the provider record was last updated."""

    model_config = {"from_attributes": True}


class Provider(ProviderInDB):
    """Schema for provider data returned in API responses. Inherits all fields from ProviderInDB."""

    pass
