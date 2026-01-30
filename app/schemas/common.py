from typing import TypeVar, Generic, List
from pydantic import BaseModel

T = TypeVar("T")


class ListResponse(BaseModel, Generic[T]):
    """Generic response model for wrapping list responses."""

    items: List[T]


class DataResponse(BaseModel, Generic[T]):
    """Generic response model for wrapping single-object responses."""

    items: T
