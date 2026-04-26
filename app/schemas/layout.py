from pydantic import BaseModel, field_validator
from typing import Optional
from uuid import UUID
from datetime import datetime
from slugify import slugify


class LayoutBase(BaseModel):
    alias: str
    name: Optional[str] = None
    html: str

    @field_validator("alias", mode="before")
    @classmethod
    def normalise_alias(cls, v: str) -> str:
        return slugify(v)


class LayoutCreate(LayoutBase):
    pass


class LayoutUpdate(BaseModel):
    alias: Optional[str] = None
    name: Optional[str] = None
    html: Optional[str] = None

    @field_validator("alias", mode="before")
    @classmethod
    def normalise_alias(cls, v: Optional[str]) -> Optional[str]:
        return slugify(v) if v is not None else v


class LayoutInDB(LayoutBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class Layout(LayoutInDB):
    pass
