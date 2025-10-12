from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID
from fastapi_pagination import Page, Params
from fastapi_pagination.ext.sqlalchemy import paginate

from app.db import get_db
from app.commands.send_email_command import SendEmailCommand
from app.providers.base import EmailSendRequest
from app.schemas.email import Email
from app.services.email_service import EmailService
from app.services.tenant_service import TenantService

router = APIRouter(
    prefix="/emails",
    tags=["emails"],
    responses={404: {"description": "Not found"}},
)

# Router for nested tenant emails collection routes
tenant_emails_router = APIRouter(
    prefix="/tenants",
    tags=["emails"],
    responses={404: {"description": "Not found"}},
)


@router.post("/send", response_model=Email, status_code=status.HTTP_200_OK)
def send_email(request: EmailSendRequest, db: Session = Depends(get_db)) -> Email:
    """
    Send an email using the tenant's configured email provider.

    This endpoint takes an email send request, resolves the tenant and provider,
    persists the email record, and sends it via the configured provider.

    Returns the result of the send operation including success status and
    provider message ID if successful.
    """
    # try:
    command = SendEmailCommand(db)
    email = command.execute(request)

    return email

    # except ValueError as e:
    #     raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    # except ProviderError as e:
    #     raise HTTPException(
    #         status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Provider error: {str(e)}"
    #     )
    # except Exception as e:
    #     raise HTTPException(
    #         status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    #         detail=f"Failed to send email: {str(e)}",
    #     )


@router.get("/{email_id}", response_model=Email)
def get_email(email_id: UUID, db: Session = Depends(get_db)) -> Email:
    """
    Get a specific email by ID.

    Args:
        email_id: The UUID of the email to retrieve
        db: Database session

    Returns:
        Dict containing the email data

    Raises:
        HTTPException: If the email is not found
    """
    email_service = EmailService(db)
    email = email_service.get_email(email_id)

    if not email:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Email not found"
        )

    return email


@tenant_emails_router.get("/{tenant_id}/emails", response_model=Page[Email])
def list_tenant_emails(
    tenant_id: UUID,
    db: Session = Depends(get_db),
    params: Params = Depends(),
) -> Page[Email]:
    """
    List all emails for a specific tenant with pagination.

    Args:
        tenant_id: The UUID of the tenant
        db: Database session
        params: Pagination parameters

    Returns:
        Dict containing paginated list of emails for the tenant

    Raises:
        HTTPException: If the tenant is not found
    """
    # Validate tenant exists
    tenant_service = TenantService(db)
    tenant = tenant_service.get_tenant(tenant_id)

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found"
        )

    # Query emails for this tenant using the email service
    email_service = EmailService(db)
    query = email_service.get_emails_by_tenant_query(tenant_id)

    return paginate(query, params)
