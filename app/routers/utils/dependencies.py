from uuid import UUID
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from app.db import get_db
from app.services.email_service import EmailService
from app.schemas.email import Email


def get_email_by_id(
    email_id: UUID,
    db: Session = Depends(get_db),
) -> Email:
    """FastAPI dependency to get an email by ID.

    Args:
        email_id: The UUID of the email to retrieve
        db: Database session dependency

    Returns:
        Email: The retrieved email

    Raises:
        HTTPException: If the email is not found
    """
    email = EmailService(db).get_email(email_id)
    if email is None:
        raise HTTPException(status_code=404, detail="Email not found")
    return email
