from fastapi import APIRouter, Depends

from app.auth.rbac import build_rbac_dependencies
from app.commands.render_content_command import RenderContentCommand
from app.db import DbSession
from app.routers.utils.dependencies import global_domain
from app.schemas.render import RenderRequest, RenderResponse

router = APIRouter(
    prefix="/render",
    tags=["render"],
    responses={404: {"description": "Layout not found"}},
)

# Previewing only reads a layout — the same grant as viewing one.
rbac = build_rbac_dependencies(resource="layout", project_resolver=global_domain)


@router.post("", response_model=RenderResponse)
def render_content(
    request: RenderRequest,
    db: DbSession,
    _authorized: bool = Depends(rbac["read"]),
) -> RenderResponse:
    return RenderContentCommand(db).execute(request)
