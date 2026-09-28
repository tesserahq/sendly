from uuid import UUID

from fastapi import HTTPException, Request

from app.db import DbSession
from app.repositories.email_repository import EmailRepository
from app.repositories.layout_repository import LayoutRepository
from app.repositories.template_repository import TemplateRepository
from app.schemas.email import Email
from app.schemas.layout import Layout
from app.schemas.template import Template


async def global_domain(_: Request) -> str:
    """RBAC domain resolver for global (non-project-scoped) resources."""
    return "*"


def get_email_by_id(
    email_id: UUID,
    db: DbSession,
) -> Email:
    email = EmailRepository(db).get_email(email_id)
    if email is None:
        raise HTTPException(status_code=404, detail="Email not found")
    return email


def get_email_with_events_by_id(
    email_id: UUID,
    db: DbSession,
) -> Email:
    email = EmailRepository(db).get_email_with_events(email_id)
    if email is None:
        raise HTTPException(status_code=404, detail="Email not found")
    return email


def get_layout_by_id(
    layout_id: UUID,
    db: DbSession,
) -> Layout:
    layout = LayoutRepository(db).get_layout(layout_id)
    if layout is None:
        raise HTTPException(status_code=404, detail="Layout not found")
    return layout


def get_template_by_id(
    template_id: UUID,
    db: DbSession,
) -> Template:
    template = TemplateRepository(db).get_template(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return template
