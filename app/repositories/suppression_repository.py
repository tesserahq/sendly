from datetime import datetime
from typing import List, Set
from uuid import UUID
from sqlalchemy.orm import Session

from app.models.email_suppression import EmailSuppression
from app.repositories.soft_delete_repository import SoftDeleteRepository


class SuppressionRepository(SoftDeleteRepository[EmailSuppression]):
    """Repository for project-scoped recipient suppressions (unsubscribes)."""

    def __init__(self, db: Session):
        super().__init__(db, EmailSuppression)

    def is_suppressed(self, project_id: UUID, email: str) -> bool:
        return (
            self.db.query(EmailSuppression)
            .filter(
                EmailSuppression.project_id == project_id,
                EmailSuppression.email == email,
            )
            .first()
            is not None
        )

    def is_suppressed_bulk(self, project_id: UUID, emails: List[str]) -> Set[str]:
        """One query, not N: return the subset of `emails` already suppressed."""
        if not emails:
            return set()
        rows = (
            self.db.query(EmailSuppression.email)
            .filter(
                EmailSuppression.project_id == project_id,
                EmailSuppression.email.in_(emails),
            )
            .all()
        )
        return {row[0] for row in rows}

    def is_suppressed_bulk_any_project(self, emails: List[str]) -> Set[str]:
        """Like is_suppressed_bulk, but for global (no project_id) broadcasts:
        a recipient suppressed in ANY project is skipped, since there's no
        single project's opt-out list to check against."""
        if not emails:
            return set()
        rows = (
            self.db.query(EmailSuppression.email)
            .filter(EmailSuppression.email.in_(emails))
            .all()
        )
        return {row[0] for row in rows}

    def create_or_update_suppression(
        self,
        *,
        project_id: UUID,
        email: str,
        unsubscribed_at: datetime,
        source: str,
    ) -> EmailSuppression:
        existing = (
            self.db.query(EmailSuppression)
            .filter(
                EmailSuppression.project_id == project_id,
                EmailSuppression.email == email,
            )
            .first()
        )
        if existing:
            existing.unsubscribed_at = unsubscribed_at
            existing.source = source
            self.db.commit()
            self.db.refresh(existing)
            return existing

        suppression = EmailSuppression(
            project_id=project_id,
            email=email,
            unsubscribed_at=unsubscribed_at,
            source=source,
        )
        self.db.add(suppression)
        self.db.commit()
        self.db.refresh(suppression)
        return suppression

    def remove_suppression(self, project_id: UUID, email: str) -> bool:
        existing = (
            self.db.query(EmailSuppression)
            .filter(
                EmailSuppression.project_id == project_id,
                EmailSuppression.email == email,
            )
            .first()
        )
        if not existing:
            return False
        self.db.delete(existing)
        self.db.commit()
        return True
