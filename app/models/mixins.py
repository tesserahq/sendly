from sqlalchemy import Column, DateTime
from datetime import datetime, timezone


class TimestampMixin:
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class SoftDeleteMixin:
    """Mixin to add soft delete functionality to models using deleted_at timestamp."""

    deleted_at = Column(DateTime, nullable=True, index=True)
