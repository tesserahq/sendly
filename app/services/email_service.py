import datetime
from typing import List, Optional
from uuid import UUID
from sqlalchemy.orm import Session
from app.models.email import Email
from app.models.email_event import EmailEvent
from app.schemas.email import (
    EmailCreate,
    EmailUpdate,
    EmailEventCreate,
    EmailEventUpdate,
)
from app.services.soft_delete_service import SoftDeleteService
from app.utils.db.filtering import apply_filters


class EmailService(SoftDeleteService[Email]):
    """Service class for managing email and email event CRUD operations."""

    def __init__(self, db: Session):
        """
        Initialize the email service.

        Args:
            db: Database session
        """
        super().__init__(db, Email)

    # ==================== Email Methods ====================

    def get_email(self, email_id: UUID) -> Optional[Email]:
        """
        Get a single email by ID.

        Args:
            email_id: The ID of the email to retrieve

        Returns:
            Optional[Email]: The email or None if not found
        """
        return self.db.query(Email).filter(Email.id == email_id).first()

    def get_emails(self, skip: int = 0, limit: int = 100) -> List[Email]:
        """
        Get a list of emails with pagination.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List[Email]: List of emails
        """
        return self.db.query(Email).offset(skip).limit(limit).all()

    def get_emails_by_tenant(
        self, tenant_id: UUID, skip: int = 0, limit: int = 100
    ) -> List[Email]:
        """
        Get all emails for a specific tenant.

        Args:
            tenant_id: The ID of the tenant
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List[Email]: List of emails for the tenant
        """
        return (
            self.db.query(Email)
            .filter(Email.tenant_id == tenant_id)
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_emails_by_tenant_query(self, tenant_id: UUID):
        """
        Get a query for all emails for a specific tenant.
        This is useful for pagination with fastapi-pagination.

        Args:
            tenant_id: The ID of the tenant

        Returns:
            Query: SQLAlchemy query object for emails of the tenant
        """
        return (
            self.db.query(Email)
            .filter(Email.tenant_id == tenant_id)
            .order_by(Email.created_at.desc())
        )

    def get_emails_by_provider(
        self, provider_id: UUID, skip: int = 0, limit: int = 100
    ) -> List[Email]:
        """
        Get all emails sent through a specific provider.

        Args:
            provider_id: The ID of the provider
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List[Email]: List of emails sent through the provider
        """
        return (
            self.db.query(Email)
            .filter(Email.provider_id == provider_id)
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_emails_by_status(
        self, status: str, skip: int = 0, limit: int = 100
    ) -> List[Email]:
        """
        Get all emails with a specific status.

        Args:
            status: The status to filter by
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List[Email]: List of emails with the specified status
        """
        return (
            self.db.query(Email)
            .filter(Email.status == status)
            .offset(skip)
            .limit(limit)
            .all()
        )

    def create_email(self, email: EmailCreate) -> Email:
        """
        Create a new email.

        Args:
            email: The email data to create

        Returns:
            Email: The created email
        """
        db_email = Email(**email.model_dump())
        self.db.add(db_email)
        self.db.commit()
        self.db.refresh(db_email)
        return db_email

    def update_email(self, email_id: UUID, email: EmailUpdate) -> Optional[Email]:
        """
        Update an existing email.

        Args:
            email_id: The ID of the email to update
            email: The updated email data

        Returns:
            Optional[Email]: The updated email or None if not found
        """
        db_email = self.db.query(Email).filter(Email.id == email_id).first()
        if db_email:
            update_data = email.model_dump(exclude_unset=True)
            for key, value in update_data.items():
                setattr(db_email, key, value)
            self.db.commit()
            self.db.refresh(db_email)
        return db_email

    def delete_email(self, email_id: UUID) -> bool:
        """
        Soft delete an email.

        Args:
            email_id: The ID of the email to delete

        Returns:
            bool: True if the email was deleted, False otherwise
        """
        return self.delete_record(email_id)

    def search(self, filters: dict) -> List[Email]:
        """
        Search emails based on dynamic filter criteria.

        Args:
            filters: A dictionary where keys are field names and values are either:
                - A direct value (e.g. {"status": "sent"})
                - A dictionary with 'operator' and 'value' keys

        Returns:
            List[Email]: Filtered list of emails matching the criteria.
        """
        query = self.db.query(Email)
        query = apply_filters(query, Email, filters)
        return query.all()

    # ==================== Email Event Methods ====================

    def get_email_event(self, event_id: UUID) -> Optional[EmailEvent]:
        """
        Get a single email event by ID.

        Args:
            event_id: The ID of the email event to retrieve

        Returns:
            Optional[EmailEvent]: The email event or None if not found
        """
        return self.db.query(EmailEvent).filter(EmailEvent.id == event_id).first()

    def get_email_events(
        self, email_id: UUID, skip: int = 0, limit: int = 100
    ) -> List[EmailEvent]:
        """
        Get all events for a specific email.

        Args:
            email_id: The ID of the email
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List[EmailEvent]: List of events for the email
        """
        return (
            self.db.query(EmailEvent)
            .filter(EmailEvent.email_id == email_id)
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_email_events_by_type(
        self, email_id: UUID, event_type: str, skip: int = 0, limit: int = 100
    ) -> List[EmailEvent]:
        """
        Get all events of a specific type for an email.

        Args:
            email_id: The ID of the email
            event_type: The type of events to retrieve
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List[EmailEvent]: List of events matching the type
        """
        return (
            self.db.query(EmailEvent)
            .filter(
                EmailEvent.email_id == email_id, EmailEvent.event_type == event_type
            )
            .offset(skip)
            .limit(limit)
            .all()
        )

    def create_email_event(self, event: EmailEventCreate) -> EmailEvent:
        """
        Create a new email event.

        Args:
            event: The email event data to create

        Returns:
            EmailEvent: The created email event
        """
        db_event = EmailEvent(**event.model_dump())
        self.db.add(db_event)
        self.db.commit()
        self.db.refresh(db_event)
        return db_event

    def update_email_event(
        self, event_id: UUID, event: EmailEventUpdate
    ) -> Optional[EmailEvent]:
        """
        Update an existing email event.

        Args:
            event_id: The ID of the email event to update
            event: The updated email event data

        Returns:
            Optional[EmailEvent]: The updated email event or None if not found
        """
        db_event = self.db.query(EmailEvent).filter(EmailEvent.id == event_id).first()
        if db_event:
            update_data = event.model_dump(exclude_unset=True)
            for key, value in update_data.items():
                setattr(db_event, key, value)
            self.db.commit()
            self.db.refresh(db_event)
        return db_event

    def delete_email_event(self, event_id: UUID) -> bool:
        """
        Delete an email event (hard delete).

        Args:
            event_id: The ID of the email event to delete

        Returns:
            bool: True if the event was deleted, False otherwise
        """
        db_event = self.db.query(EmailEvent).filter(EmailEvent.id == event_id).first()
        if db_event:
            self.db.delete(db_event)
            self.db.commit()
            return True
        return False

    def search_email_events(self, filters: dict) -> List[EmailEvent]:
        """
        Search email events based on dynamic filter criteria.

        Args:
            filters: A dictionary where keys are field names and values are either:
                - A direct value (e.g. {"event_type": "delivered"})
                - A dictionary with 'operator' and 'value' keys

        Returns:
            List[EmailEvent]: Filtered list of email events matching the criteria.
        """
        query = self.db.query(EmailEvent)
        query = apply_filters(query, EmailEvent, filters)
        return query.all()

    def restore_email(self, email_id: UUID) -> bool:
        """Restore a soft-deleted email by setting deleted_at to None."""
        return self.restore_record(email_id)

    def hard_delete_email(self, email_id: UUID) -> bool:
        """Permanently delete a email from the database."""
        return self.hard_delete_record(email_id)

    def get_deleted_emails(self, skip: int = 0, limit: int = 100) -> List[Email]:
        """Get all soft-deleted emails."""
        return self.get_deleted_records(skip, limit)

    def get_deleted_email(self, email_id: UUID) -> Optional[Email]:
        """Get a single soft-deleted email by ID."""
        return self.get_deleted_record(email_id)

    def get_emails_deleted_after(self, date: datetime) -> List[Email]:
        """Get emails deleted after a specific date."""
        return self.get_records_deleted_after(date)
