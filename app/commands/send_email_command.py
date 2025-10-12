from __future__ import annotations
from sqlalchemy.orm import Session

from app.models.email import Email
from app.providers.registry import get_provider
from datetime import datetime
from app.services.tenant_service import TenantService
from app.services.email_service import EmailService
from app.schemas.email import EmailCreate, EmailEventCreate, EmailUpdate
from app.constants.email import EmailStatus
from app.providers.base import EmailSendRequest
from mako.template import Template


class SendEmailCommand:
    def __init__(self, db: Session):
        self.db = db
        self.tenant_service = TenantService(db)
        self.email_service = EmailService(db)

    def execute(self, req: EmailSendRequest) -> Email:
        # 1) resolve tenant/provider
        tenant = self.tenant_service.get_tenant(req.tenant_id)
        if not tenant:
            raise ValueError("tenant not found")

        provider = tenant.provider
        email_provider = get_provider(provider.slug(), tenant.provider_settings)

        # TODO: We should probably move this into its own class and out
        # of the provider class
        html_tmpl = Template(req.html)
        # text_tmpl = Template(
        #     req.text
        # )
        html = html_tmpl.render(**req.template_variables)
        # text = text_tmpl.render(**req.template_variables)

        # 2) persist initial email row
        email = EmailCreate(
            tenant_id=tenant.id,
            provider_id=provider.id,
            from_email=str(req.from_email),
            to_email=str(req.personalization.to[0]),
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
