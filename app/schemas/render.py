from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class RenderRequest(BaseModel):
    """Request body for POST /render: content to preview, rendered exactly as
    an inline send would render it (see EmailRenderingService.render_content)."""

    html: str
    subject: str = ""
    layout_id: Optional[UUID] = None
    """Layout to wrap `html` in. id wins over alias, as on broadcasts."""
    layout_alias: Optional[str] = None
    template_variables: Dict[str, Any] = Field(default_factory=dict)


class RenderResponse(BaseModel):
    html: str
    subject: str
