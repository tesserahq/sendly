from __future__ import annotations
from sqlalchemy.orm import Session

from app.models.email import Email
from app.repositories.email_repository import EmailRepository
from app.schemas.email import EmailCreate
from app.constants.email import EmailStatus
from app.providers.base import EmailCreateRequest
from mako.template import Template
from app.providers.registry import get_default_provider
from app.services.email_lifecycle_service import EmailLifecycleService


class SendEmailCommand:
    def __init__(self, db: Session):
        self.db = db
        self.email_service = EmailRepository(db)
        self.lifecycle = EmailLifecycleService(self.email_service)

    def execute(self, req: EmailCreateRequest) -> Email:
        """
        Send an email using the default email provider.
        """
        email_provider = get_default_provider()

        # TODO: We should probably move this into its own class and out
        # of the provider class
        try:
            html_tmpl = Template(req.html)
            # text_tmpl = Template(
            #     req.text
            # )
            html = html_tmpl.render(**req.template_variables)
            # text = text_tmpl.render(**req.template_variables)
        except NameError as e:
            raise ValueError(
                f"Template rendering failed: undefined variable in template. "
                f"Template variables provided: {list(req.template_variables.keys())}. "
                f"Error: {str(e)}"
            )

        # 2) persist initial email row
        email_create = EmailCreate(
            project_id=req.project_id,
            provider=email_provider.provider_id,
            from_email=str(req.from_email),
            to_email=str(req.to[0]),
            subject=req.subject,
            body=html,
            status=EmailStatus.QUEUED,
        )
        email = self.email_service.create_email(email_create)

        # 3) call provider
        result = email_provider.send_email(req.model_copy(update={"html": html}))

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
