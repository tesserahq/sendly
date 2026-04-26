from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional
from uuid import UUID
from datetime import datetime
from slugify import slugify


class TemplateBase(BaseModel):
    alias: str
    name: Optional[str] = None
    subject: str
    html: str
    from_email: Optional[EmailStr] = None
    reply_to: Optional[EmailStr] = None
    layout_id: Optional[UUID] = None

    @field_validator("alias", mode="before")
    @classmethod
    def normalise_alias(cls, v: str) -> str:
        return slugify(v)


class TemplateCreate(TemplateBase):
    pass


class TemplateUpdate(BaseModel):
    alias: Optional[str] = None
    name: Optional[str] = None
    subject: Optional[str] = None
    html: Optional[str] = None
    from_email: Optional[EmailStr] = None
    reply_to: Optional[EmailStr] = None
    layout_id: Optional[UUID] = None

    @field_validator("alias", mode="before")
    @classmethod
    def normalise_alias(cls, v: Optional[str]) -> Optional[str]:
        return slugify(v) if v is not None else v


class TemplateInDB(TemplateBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class Template(TemplateInDB):
    pass
