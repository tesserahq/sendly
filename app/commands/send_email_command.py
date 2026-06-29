from __future__ import annotations
import logging
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.models.email import Email
from app.models.template import Template
from app.repositories.email_repository import EmailRepository
from app.repositories.template_repository import TemplateRepository
from app.schemas.email import EmailCreate
from app.constants.email import EmailStatus
from app.providers.base import EmailCreateRequest
from app.providers.provider_errors import ProviderError
from mako.template import Template as MakoTemplate
from mako.exceptions import MakoException
from app.providers.registry import get_default_provider
from app.services.email_lifecycle_service import EmailLifecycleService

logger = logging.getLogger(__name__)


class SendEmailCommand:
    def __init__(self, db: Session):
        self.db = db
        self.email_service = EmailRepository(db)
        self.lifecycle = EmailLifecycleService(self.email_service)

    def execute(self, req: EmailCreateRequest) -> Email:
        using_template = req.template_id is not None or req.template_alias is not None
        using_inline = req.html is not None

        if using_template and using_inline:
            raise HTTPException(
                status_code=400,
                detail="Cannot specify both a template reference and inline html.",
            )

        if using_template:
            html, subject, from_email = self._resolve_template(req)
        else:
            html, subject, from_email = self._resolve_inline(req)

        email_provider = get_default_provider()

        email_create = EmailCreate(
            project_id=req.project_id,
            provider=email_provider.provider_id,
            from_email=from_email,
            to_email=str(req.to[0]),
            subject=subject,
            body=html,
            status=EmailStatus.QUEUED,
        )
        email = self.email_service.create_email(email_create)

        try:
            result = email_provider.send_email(
                req.model_copy(
                    update={"html": html, "subject": subject, "from_email": from_email}
                )
            )
        except ProviderError as e:
            return self.lifecycle.record_send_failure(
                email=email,
                error_message=str(e),
            )

        if result.ok:
            return self.lifecycle.record_send_success(
                email=email,
                provider_message_id=result.provider_message_id,
            )
        else:
            return self.lifecycle.record_send_failure(
                email=email,
                error_code=result.error_code,
                error_message=result.error_message,
            )

    def _resolve_template(self, req: EmailCreateRequest) -> tuple[str, str, str]:
        template = self._fetch_template(req)

        if template.layout:
            rendered_content = self._render(template.html, **req.template_variables)
            html = self._render(
                template.layout.html, content=rendered_content, **req.template_variables
            )
        else:
            if template.layout_id is not None:
                # layout_id is set but layout is None — it was soft-deleted
                logger.warning(
                    "Template %s references layout_id %s which no longer exists; "
                    "sending without layout.",
                    template.id,
                    template.layout_id,
                )
            html = self._render(template.html, **req.template_variables)
        subject = self._render(template.subject, **req.template_variables)

        from_email = str(req.from_email or template.from_email or "")
        if not from_email:
            raise HTTPException(
                status_code=422,
                detail=(
                    "from_email is required: provide it in the request or set a "
                    "default on the template."
                ),
            )

        return html, subject, from_email

    def _resolve_inline(self, req: EmailCreateRequest) -> tuple[str, str, str]:
        if not req.from_email:
            raise HTTPException(
                status_code=422,
                detail="from_email is required when sending with inline html.",
            )
        if not req.subject:
            raise HTTPException(
                status_code=422,
                detail="subject is required when sending with inline html.",
            )
        if not req.html:
            raise HTTPException(
                status_code=422,
                detail="html is required when not using a template.",
            )

        html = self._render(req.html, **req.template_variables)
        return html, req.subject, str(req.from_email)

    def _fetch_template(self, req: EmailCreateRequest) -> Template:
        repo = TemplateRepository(self.db)
        template = None

        if req.template_id:
            template = repo.get_template(req.template_id)
        elif req.template_alias:
            template = repo.get_template_by_alias(req.template_alias)

        if template is None:
            raise HTTPException(status_code=404, detail="Template not found.")

        return template

    @staticmethod
    def _render(template_str: str, **variables) -> str:
        try:
            return MakoTemplate(template_str).render(**variables)
        except NameError as e:
            raise ValueError(
                f"Template rendering failed: undefined variable. "
                f"Variables provided: {list(variables.keys())}. Error: {str(e)}"
            )
        except MakoException as e:
            raise HTTPException(
                status_code=422,
                detail=f"Template syntax error: {str(e)}",
            )
