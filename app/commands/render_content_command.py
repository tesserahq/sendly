"""Preview rendering: no persistence, no provider, no side effects.

Goes through EmailRenderingService.render_content — the same path inline
sends use — so a preview matches what would actually be sent.
"""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.schemas.render import RenderRequest, RenderResponse
from app.services.email_rendering_service import (
    EmailRenderingService,
    LayoutNotFoundError,
    MissingFieldError,
    TemplateSyntaxError,
)


class RenderContentCommand:
    def __init__(self, db: Session):
        self.rendering = EmailRenderingService(db)

    def execute(self, req: RenderRequest) -> RenderResponse:
        try:
            layout_html = self.rendering.resolve_layout_html(
                req.layout_id, req.layout_alias
            )
            rendered = self.rendering.render_content(
                req.html,
                req.subject,
                req.template_variables,
                layout_html=layout_html,
            )
        except LayoutNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except (MissingFieldError, TemplateSyntaxError) as e:
            raise HTTPException(status_code=422, detail=str(e))
        return RenderResponse(html=rendered.html, subject=rendered.subject)
