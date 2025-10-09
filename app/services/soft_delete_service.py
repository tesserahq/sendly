from typing import List, Optional, TypeVar, Generic, Type
from uuid import UUID
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.db import Base

# Generic type for SQLAlchemy models that have id and deleted_at fields
T = TypeVar("T", bound=Base)


class SoftDeleteService(Generic[T]):
    """
    Generic service class that provides soft delete functionality for any model.

    This class can be inherited by other services to add soft delete capabilities
    without duplicating code.
    """

    def __init__(self, db: Session, model_class: Type[T]):
        """
        Initialize the soft delete service.

        Args:
            db: Database session
            model_class: The SQLAlchemy model class that supports soft deletes
        """
        self.db = db
        self.model_class = model_class

    def delete_record(self, record_id: UUID) -> bool:
        """
        Soft delete a record by setting deleted_at timestamp.

        Args:
            record_id: The ID of the record to soft delete

        Returns:
            bool: True if the record was found and deleted, False otherwise
        """
        record = (
            self.db.query(self.model_class)
            .filter(self.model_class.id == record_id)
            .first()
        )

        if record:
            record.deleted_at = datetime.now(timezone.utc)
            self.db.commit()
            return True
        return False

    def delete_records(self, record_ids: List[UUID]) -> bool:
        """
        Soft delete multiple records by setting deleted_at timestamp.
        """
        records = (
            self.db.query(self.model_class)
            .filter(self.model_class.id.in_(record_ids))
            .all()
        )
        for record in records:
            record.deleted_at = datetime.now(timezone.utc)
            self.db.commit()
        return True

    def restore_record(self, record_id: UUID) -> bool:
        """
        Restore a soft-deleted record by setting deleted_at to None.

        Args:
            record_id: The ID of the record to restore

        Returns:
            bool: True if the record was found and restored, False otherwise
        """
        record = (
            self.db.query(self.model_class)
            .execution_options(skip_soft_delete_filter=True)
            .filter(self.model_class.id == record_id)
            .first()
        )

        if record:
            record.deleted_at = None
            self.db.commit()
            return True
        return False

    def hard_delete_record(self, record_id: UUID) -> bool:
        """
        Permanently delete a record from the database.

        Args:
            record_id: The ID of the record to permanently delete

        Returns:
            bool: True if the record was found and deleted, False otherwise
        """
        record = (
            self.db.query(self.model_class)
            .filter(self.model_class.id == record_id)
            .first()
        )

        if record:
            self.db.delete(record)
            self.db.commit()
            return True
        return False

    def get_deleted_records(self, skip: int = 0, limit: int = 100) -> List[T]:
        """
        Get all soft-deleted records.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List[T]: List of soft-deleted records
        """
        return (
            self.db.query(self.model_class)
            .execution_options(skip_soft_delete_filter=True)
            .filter(self.model_class.deleted_at.isnot(None))
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_deleted_record(self, record_id: UUID) -> Optional[T]:
        """
        Get a single soft-deleted record by ID.

        Args:
            record_id: The ID of the record to retrieve

        Returns:
            Optional[T]: The soft-deleted record or None if not found
        """
        return (
            self.db.query(self.model_class)
            .execution_options(skip_soft_delete_filter=True)
            .filter(self.model_class.id == record_id)
            .filter(self.model_class.deleted_at.isnot(None))
            .first()
        )

    def get_records_deleted_after(self, date: datetime) -> List[T]:
        """
        Get records deleted after a specific date.

        Args:
            date: The date to filter from

        Returns:
            List[T]: List of records deleted after the specified date
        """
        return (
            self.db.query(self.model_class)
            .execution_options(skip_soft_delete_filter=True)
            .filter(self.model_class.deleted_at >= date)
            .all()
        )

    def get_record_any_status(self, record_id: UUID) -> Optional[T]:
        """
        Get a record regardless of deletion status (deleted or not).

        Args:
            record_id: The ID of the record to retrieve

        Returns:
            Optional[T]: The record or None if not found
        """
        return (
            self.db.query(self.model_class)
            .execution_options(skip_soft_delete_filter=True)
            .filter(self.model_class.id == record_id)
            .first()
        )
