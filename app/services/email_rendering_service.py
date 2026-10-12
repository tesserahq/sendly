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
import re
import types
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional, Protocol

from mako.exceptions import MakoException
from mako.template import Template as MakoTemplate
from sqlalchemy.orm import Session

from app.models.template import Template
from app.providers.base import EmailCreateRequest
from app.repositories.layout_repository import LayoutRepository
from app.repositories.template_repository import TemplateRepository

logger = logging.getLogger(__name__)


class ContentOptions(Protocol):
    """Structural shape shared by EmailCreateRequest and ContentSpec — the
    fields `validate()` needs, regardless of which caller passes them in.
    (ContentSpec additionally carries layout_id/layout_alias, which
    `validate()` reads when present.)"""

    template_id: Optional[Any]
    template_alias: Optional[str]
    html: Optional[str]
    subject: Optional[str]
    from_email: Optional[str]


class RenderingError(Exception):
    """Base class for EmailRenderingService errors."""


class TemplateNotFoundError(RenderingError):
    """Raised when template_id/template_alias doesn't resolve to a Template."""


class LayoutNotFoundError(RenderingError):
    """Raised when an inline layout_id/layout_alias doesn't resolve to a
    Layout (missing or soft-deleted). Unlike a template's dangling layout,
    which degrades to sending without one, an explicitly requested layout
    must exist — nothing goes out half-styled."""


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
    reply_to: Optional[str] = None


@dataclass
class RenderedBody:
    html: str
    subject: str


class EmailRenderingService:
    def __init__(self, db: Session):
        self.db = db

    def resolve(
        self, req: EmailCreateRequest, layout_html: Optional[str] = None
    ) -> RenderedContent:
        """`layout_html` is an already-resolved layout to wrap inline html in —
        the broadcast prepare stage passes the snapshot frozen at accept time
        (ContentSpec.layout_html). It never applies to templates, which carry
        their own layout."""
        using_template = req.template_id is not None or req.template_alias is not None
        if using_template:
            return self.resolve_template(req)
        return self.resolve_inline(req, layout_html=layout_html)

    def render_content(
        self,
        html: str,
        subject: str,
        variables: dict[str, Any],
        layout_html: Optional[str] = None,
    ) -> RenderedBody:
        """Render a body (wrapped in `layout_html`, passed as `content`, when
        given) and a subject with the same variables. The one rendering path
        shared by templates, inline sends, and previews, so they can't drift."""
        body = self.render(html, **variables)
        if layout_html is not None:
            body = self.render(layout_html, content=body, **variables)
        return RenderedBody(html=body, subject=self.render(subject, **variables))

    def resolve_layout_html(
        self, layout_id: Optional[Any], layout_alias: Optional[str]
    ) -> Optional[str]:
        """Resolve an inline layout reference to its html, or None when no
        reference was given. id wins over alias, matching template lookup."""
        if layout_id is None and layout_alias is None:
            return None
        repo = LayoutRepository(self.db)
        if layout_id is not None:
            layout = repo.get_layout(layout_id)
        else:
            layout = repo.get_layout_by_alias(layout_alias)
        if layout is None:
            raise LayoutNotFoundError("Layout not found.")
        return layout.html

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

        using_layout = (
            getattr(content, "layout_id", None) is not None
            or getattr(content, "layout_alias", None) is not None
        )

        if using_template and using_inline:
            raise ConflictingContentError(
                "Cannot specify both a template reference and inline html."
            )
        if using_template and using_layout:
            raise ConflictingContentError(
                "A layout reference can only be used with inline html; a "
                "template uses its own layout."
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

        if template.layout is None and template.layout_id is not None:
            # layout_id is set but layout is None — it was soft-deleted
            logger.warning(
                "Template %s references layout_id %s which no longer exists; "
                "sending without layout.",
                template.id,
                template.layout_id,
            )
        rendered = self.render_content(
            template.html,
            template.subject,
            req.template_variables,
            layout_html=template.layout.html if template.layout else None,
        )
        html, subject = rendered.html, rendered.subject

        from_email = str(req.from_email or template.from_email or "")
        if not from_email:
            raise MissingFieldError(
                "from_email is required: provide it in the request or set a "
                "default on the template."
            )

        reply_to = req.reply_to or template.reply_to
        reply_to = str(reply_to) if reply_to else None

        return RenderedContent(
            html=html, subject=subject, from_email=from_email, reply_to=reply_to
        )

    def resolve_inline(
        self, req: EmailCreateRequest, layout_html: Optional[str] = None
    ) -> RenderedContent:
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

        rendered = self.render_content(
            req.html, req.subject, req.template_variables, layout_html=layout_html
        )
        return RenderedContent(
            html=rendered.html,
            subject=rendered.subject,
            from_email=str(req.from_email),
            reply_to=str(req.reply_to) if req.reply_to else None,
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

    # Mako's own NameError for an undefined variable only ever says
    # "Undefined" — it never names the variable. Its compiled Python source
    # does, though: every top-level identifier the template needs from the
    # caller is fetched via `context.get('name', UNDEFINED)`, so scraping
    # that out of the compiled code lets us name the actual missing
    # variable(s) instead of just listing what was supplied.
    _CONTEXT_GET_RE = re.compile(r"context\.get\('([^']+)',\s*UNDEFINED\)")

    @staticmethod
    def _referenced_identifiers(template_str: str) -> set[str]:
        return set(
            EmailRenderingService._CONTEXT_GET_RE.findall(
                MakoTemplate(template_str).code
            )
        )

    @staticmethod
    def render(template_str: str, **variables) -> str:
        variables.setdefault("year", datetime.now().year)
        variables = {
            k: EmailRenderingService._to_namespace(v) for k, v in variables.items()
        }
        try:
            return MakoTemplate(template_str).render(**variables)
        except (NameError, AttributeError) as e:
            provided = sorted(k for k in variables if k != "year")
            missing = sorted(
                EmailRenderingService._referenced_identifiers(template_str)
                - set(provided)
            )
            missing_clause = f"Missing variable(s): {missing}. " if missing else ""
            raise MissingFieldError(
                f"Template rendering failed: a required variable is missing or undefined. "
                f"{missing_clause}Variables provided: {provided}. Error: {e}"
            ) from e
        except MakoException as e:
            raise TemplateSyntaxError(f"Template syntax error: {str(e)}") from e
