from pydantic import BaseModel, EmailStr, field_validator
from typing import List, Optional
from uuid import UUID
from datetime import datetime
from slugify import slugify

from app.schemas.layout import Layout
from app.schemas.user import UserSummary


def _normalise_tags(v: Optional[List[str]]) -> Optional[List[str]]:
    if v is None:
        return v
    seen = set()
    normalised = []
    for tag in v:
        tag = tag.strip()
        if not tag:
            raise ValueError("tags must not contain empty strings")
        if tag not in seen:
            seen.add(tag)
            normalised.append(tag)
    return normalised


class TemplateBase(BaseModel):
    alias: str
    name: Optional[str] = None
    subject: str
    html: str
    from_email: Optional[EmailStr] = None
    reply_to: Optional[EmailStr] = None
    layout_id: Optional[UUID] = None
    tags: Optional[List[str]] = None

    @field_validator("alias", mode="before")
    @classmethod
    def normalise_alias(cls, v: str) -> str:
        return slugify(v)

    @field_validator("tags")
    @classmethod
    def normalise_tags(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        return _normalise_tags(v)


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
    tags: Optional[List[str]] = None

    @field_validator("alias", mode="before")
    @classmethod
    def normalise_alias(cls, v: Optional[str]) -> Optional[str]:
        return slugify(v) if v is not None else v

    @field_validator("tags")
    @classmethod
    def normalise_tags(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        return _normalise_tags(v)


class TemplateInDB(TemplateBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TemplateClone(BaseModel):
    alias: Optional[str] = None
    name: Optional[str] = None
    tags: Optional[List[str]] = None

    @field_validator("alias", mode="before")
    @classmethod
    def normalise_alias(cls, v: Optional[str]) -> Optional[str]:
        return slugify(v) if v is not None else v

    @field_validator("tags")
    @classmethod
    def normalise_tags(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        return _normalise_tags(v)


class Template(TemplateInDB):
    layout: Optional[Layout] = None
    created_by: Optional[UserSummary] = None
