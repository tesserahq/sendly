"""Shared template-resolution/Mako-rendering logic for single-send and broadcast-send.

Extracted from SendEmailCommand so template behavior (variable interpolation,
layout wrapping, error handling) cannot diverge between the two paths.

Raises plain exceptions rather than HTTPException: this service is called both
from a FastAPI request (SendEmailCommand) and from a Celery task with no HTTP
context (prepare_broadcast_chunk_task), where a per-recipient failure must not
block the rest of a chunk.
"""

from __future__ import annotations

import logging
import types
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional, Protocol

from mako.exceptions import MakoException
from mako.template import Template as MakoTemplate
from sqlalchemy.orm import Session

from app.models.template import Template
from app.providers.base import EmailCreateRequest
from app.repositories.template_repository import TemplateRepository

logger = logging.getLogger(__name__)


class ContentOptions(Protocol):
    """Structural shape shared by EmailCreateRequest and ContentSpec — the
    fields `validate()` needs, regardless of which caller passes them in."""

    template_id: Optional[Any]
    template_alias: Optional[str]
    html: Optional[str]
    subject: Optional[str]
    from_email: Optional[str]


class RenderingError(Exception):
    """Base class for EmailRenderingService errors."""


class TemplateNotFoundError(RenderingError):
    """Raised when template_id/template_alias doesn't resolve to a Template."""


class MissingFieldError(RenderingError):
    """Raised when a required field (from_email/subject/html/variable) is missing."""


class TemplateSyntaxError(RenderingError):
    """Raised when the Mako template string itself fails to compile/render."""


class ConflictingContentError(RenderingError):
    """Raised when both a template reference and inline html are specified."""


@dataclass
class RenderedContent:
    html: str
    subject: str
    from_email: str


class EmailRenderingService:
    def __init__(self, db: Session):
        self.db = db

    def resolve(self, req: EmailCreateRequest) -> RenderedContent:
        using_template = req.template_id is not None or req.template_alias is not None
        if using_template:
            return self.resolve_template(req)
        return self.resolve_inline(req)

    def validate(self, content: ContentOptions) -> None:
        """Validate content-option requirements without rendering.

        These checks (template-vs-inline exclusivity, a resolvable template,
        required from_email/subject/html) depend only on the shared content
        — never on per-recipient personalization — so they're safe to run
        once, synchronously, before fanning content out to every recipient
        (see SendBroadcastCommand). Without this, a content-level mistake
        fails identically, silently, for every recipient deep in the async
        prepare stage instead of surfacing to the caller immediately.
        """
        using_template = (
            content.template_id is not None or content.template_alias is not None
        )
        using_inline = content.html is not None

        if using_template and using_inline:
            raise ConflictingContentError(
                "Cannot specify both a template reference and inline html."
            )
        if not using_template and not using_inline:
            raise MissingFieldError(
                "Either a template reference or inline html is required."
            )

        if using_template:
            template = self._fetch_template(content)
            if not (content.from_email or template.from_email):
                raise MissingFieldError(
                    "from_email is required: provide it in the request or set a "
                    "default on the template."
                )
        else:
            if not content.from_email:
                raise MissingFieldError(
                    "from_email is required when sending with inline html."
                )
            if not content.subject:
                raise MissingFieldError(
                    "subject is required when sending with inline html."
                )
            if not content.html:
                raise MissingFieldError("html is required when not using a template.")

    def resolve_template(self, req: EmailCreateRequest) -> RenderedContent:
        template = self._fetch_template(req)

        if template.layout:
            rendered_content = self.render(template.html, **req.template_variables)
            html = self.render(
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
            html = self.render(template.html, **req.template_variables)
        subject = self.render(template.subject, **req.template_variables)

        from_email = str(req.from_email or template.from_email or "")
        if not from_email:
            raise MissingFieldError(
                "from_email is required: provide it in the request or set a "
                "default on the template."
            )

        return RenderedContent(html=html, subject=subject, from_email=from_email)

    def resolve_inline(self, req: EmailCreateRequest) -> RenderedContent:
        if not req.from_email:
            raise MissingFieldError(
                "from_email is required when sending with inline html."
            )
        if not req.subject:
            raise MissingFieldError(
                "subject is required when sending with inline html."
            )
        if not req.html:
            raise MissingFieldError("html is required when not using a template.")

        html = self.render(req.html, **req.template_variables)
        return RenderedContent(
            html=html, subject=req.subject, from_email=str(req.from_email)
        )

    def _fetch_template(self, req: ContentOptions) -> Template:
        repo = TemplateRepository(self.db)
        template = None

        if req.template_id:
            template = repo.get_template(req.template_id)
        elif req.template_alias:
            template = repo.get_template_by_alias(req.template_alias)

        if template is None:
            raise TemplateNotFoundError("Template not found.")

        return template

    @staticmethod
    def _to_namespace(obj):
        if isinstance(obj, dict):
            return types.SimpleNamespace(
                **{k: EmailRenderingService._to_namespace(v) for k, v in obj.items()}
            )
        return obj

    @staticmethod
    def render(template_str: str, **variables) -> str:
        variables.setdefault("year", datetime.now().year)
        variables = {
            k: EmailRenderingService._to_namespace(v) for k, v in variables.items()
        }
        try:
            return MakoTemplate(template_str).render(**variables)
        except (NameError, AttributeError) as e:
            raise MissingFieldError(
                f"Template rendering failed: a required variable is missing or undefined. "
                f"Variables provided: {[k for k in variables if k != 'year']}. Error: {e}"
            ) from e
        except MakoException as e:
            raise TemplateSyntaxError(f"Template syntax error: {str(e)}") from e
