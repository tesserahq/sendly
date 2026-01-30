from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from uuid import UUID
from fastapi_pagination import Page, Params
from fastapi_pagination.ext.sqlalchemy import paginate

from app.db import get_db
from app.commands.send_email_command import SendEmailCommand
from app.providers.base import EmailCreateRequest
from app.schemas.email import Email
from app.services.email_service import EmailService
from app.auth.rbac import build_rbac_dependencies
from fastapi import Request
from typing import Annotated
from app.routers.utils.dependencies import get_email_by_id

router = APIRouter(
    prefix="/emails",
    tags=["emails"],
    responses={404: {"description": "Not found"}},
)


async def infer_project(request: Request) -> Optional[str]:
    """
    Infer the project from the query parameter 'tags' by extracting the value for 'project_id'.
    The 'tags' parameter is expected to be an array of strings in the format 'key:value'.
    Returns the value of 'project_id' if present, otherwise returns '*'.
    """
    # First, check for explicit project parameter
    project_id = request.query_params.get("project_id")
    if project_id:
        return project_id

    return "*"


RESOURCE = "email"
rbac = build_rbac_dependencies(
    resource=RESOURCE,
    project_resolver=infer_project,
)


@router.post("", response_model=Email, status_code=status.HTTP_200_OK)
def create_email(request: EmailCreateRequest, db: Session = Depends(get_db)) -> Email:
    """
    Create a new email.
    """
    command = SendEmailCommand(db)
    email = command.execute(request)

    return email


@router.get("/{email_id}", response_model=Email)
def get_email(email: Email = Depends(get_email_by_id)) -> Email:
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
    return email


@router.get("", response_model=Page[Email])
def list_emails(
    project_id: Annotated[
        Optional[UUID],
        Query(description="Project ID to filter emails by"),
    ] = None,
    db: Session = Depends(get_db),
    params: Params = Depends(),
) -> Page[Email]:
    """
    List all emails for a specific project with pagination.

    Args:
        project_id: The UUID of the project
        db: Database session
        params: Pagination parameters

    Returns:
        Dict containing paginated list of emails for the project

    Raises:
        HTTPException: If the project is not found
    """

    email_service = EmailService(db)
    if project_id:
        query = email_service.get_emails_by_project_query(project_id)
    else:
        query = email_service.get_emails_query()

    return paginate(query, params)
