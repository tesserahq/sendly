from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi_pagination import Page, Params
from fastapi_pagination.ext.sqlalchemy import paginate
from tessera_sdk.server.dependencies.auth import get_current_user

from app.auth.rbac import build_rbac_dependencies
from app.commands.layouts.create_layout_command import CreateLayoutCommand
from app.commands.layouts.delete_layout_command import DeleteLayoutCommand
from app.commands.layouts.update_layout_command import UpdateLayoutCommand
from app.db import DbSession
from app.models.user import User
from app.repositories.layout_repository import LayoutRepository
from app.routers.utils.dependencies import get_layout_by_id, global_domain
from app.schemas.layout import Layout, LayoutCreate, LayoutUpdate

router = APIRouter(
    prefix="/layouts",
    tags=["layouts"],
    responses={404: {"description": "Not found"}},
)

RESOURCE = "layout"
rbac = build_rbac_dependencies(resource=RESOURCE, project_resolver=global_domain)


@router.post("", response_model=Layout, status_code=status.HTTP_201_CREATED)
def create_layout(
    request: LayoutCreate,
    db: DbSession,
    current_user: User = Depends(get_current_user),
    _authorized: bool = Depends(rbac["create"]),
) -> Layout:
    return CreateLayoutCommand(db).execute(request, created_by_id=current_user.id)


@router.get("", response_model=Page[Layout])
def list_layouts(
    db: DbSession,
    params: Params = Depends(),
    _authorized: bool = Depends(rbac["read"]),
) -> Page[Layout]:
    return paginate(LayoutRepository(db).get_layouts_query(), params)


@router.get("/{layout_id}", response_model=Layout)
def get_layout(
    layout: Layout = Depends(get_layout_by_id),
    _authorized: bool = Depends(rbac["read"]),
) -> Layout:
    return layout


@router.patch("/{layout_id}", response_model=Layout)
def update_layout(
    layout_id: UUID,
    request: LayoutUpdate,
    db: DbSession,
    _authorized: bool = Depends(rbac["update"]),
) -> Layout:
    result = UpdateLayoutCommand(db).execute(layout_id, request)
    if result is None:
        raise HTTPException(status_code=404, detail="Layout not found")
    return result


@router.delete("/{layout_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_layout(
    layout_id: UUID,
    db: DbSession,
    _authorized: bool = Depends(rbac["delete"]),
) -> None:
    deleted = DeleteLayoutCommand(db).execute(layout_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Layout not found")
