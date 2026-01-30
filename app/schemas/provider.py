"""Pydantic schemas for email provider API responses."""

from __future__ import annotations

from pydantic import BaseModel


class ProviderRead(BaseModel):
    """Public provider metadata for list/detail responses."""

    id: str
    name: str
    enabled: bool
    default: bool
    site: str | None = None
