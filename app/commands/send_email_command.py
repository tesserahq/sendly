from __future__ import annotations
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.models.email import Email
from app.repositories.email_repository import EmailRepository
from app.schemas.email import EmailCreate
from app.constants.email import EmailStatus
from app.providers.base import EmailCreateRequest
from app.providers.provider_errors import ProviderError
from app.providers.registry import get_default_provider
from app.services.email_lifecycle_service import EmailLifecycleService
from app.services.email_rendering_service import (
    EmailRenderingService,
    MissingFieldError,
    TemplateNotFoundError,
    TemplateSyntaxError,
)


class SendEmailCommand:
    def __init__(self, db: Session):
        self.db = db
        self.email_service = EmailRepository(db)
        self.lifecycle = EmailLifecycleService(self.email_service)
        self.rendering = EmailRenderingService(db)

    def execute(self, req: EmailCreateRequest) -> Email:
        using_template = req.template_id is not None or req.template_alias is not None
        using_inline = req.html is not None

        if using_template and using_inline:
            raise HTTPException(
                status_code=400,
                detail="Cannot specify both a template reference and inline html.",
            )

        try:
            rendered = self.rendering.resolve(req)
        except TemplateNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except MissingFieldError as e:
            raise HTTPException(status_code=422, detail=str(e))
        except TemplateSyntaxError as e:
            raise HTTPException(status_code=422, detail=str(e))

        email_provider = get_default_provider()

        email_create = EmailCreate(
            project_id=req.project_id,
            provider=email_provider.provider_id,
            from_email=rendered.from_email,
            to_email=str(req.to[0]),
            subject=rendered.subject,
            body=rendered.html,
            status=EmailStatus.QUEUED,
            tags=req.tags,
            metadata_=req.metadata,
        )
        email = self.email_service.create_email(email_create)

        try:
            result = email_provider.send_email(
                req.model_copy(
                    update={
                        "html": rendered.html,
                        "subject": rendered.subject,
                        "from_email": rendered.from_email,
                    }
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
