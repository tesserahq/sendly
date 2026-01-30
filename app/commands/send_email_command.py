from __future__ import annotations
from sqlalchemy.orm import Session

from app.models.email import Email
from datetime import datetime
from app.services.email_service import EmailService
from app.schemas.email import EmailCreate, EmailEventCreate, EmailUpdate
from app.constants.email import EmailStatus
from app.providers.base import EmailCreateRequest
from mako.template import Template
from app.providers.registry import get_default_provider


class SendEmailCommand:
    def __init__(self, db: Session):
        self.db = db
        self.email_service = EmailService(db)

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
        email = EmailCreate(
            project_id=req.project_id,
            provider=email_provider.provider_id,
            from_email=str(req.from_email),
            to_email=str(req.to[0]),
            subject=req.subject,
            body=html,
            status=EmailStatus.QUEUED,
        )
        email = self.email_service.create_email(email)

        # 3) call provider
        result = email_provider.send_email(req.model_copy(update={"html": html}))

        now = datetime.utcnow()
        if result.ok:
            email_update = EmailUpdate(
                status=EmailStatus.SENT,
                sent_at=now,
                provider_message_id=result.provider_message_id,
            )
            updated_email = self.email_service.update_email(email.id, email_update)
        else:
            email_update = EmailUpdate(
                status=EmailStatus.FAILED,
                updated_at=now,
            )
            updated_email = self.email_service.update_email(email.id, email_update)
            self.email_service.create_email_event(
                EmailEventCreate(
                    email_id=email.id,
                    event_type="failed",
                    event_timestamp=now,
                    details={
                        "error_code": result.error_code,
                        "error_message": result.error_message,
                    },
                )
            )

        return updated_email
