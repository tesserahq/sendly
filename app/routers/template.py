from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID
from fastapi_pagination import Page, Params
from fastapi_pagination.ext.sqlalchemy import paginate

from app.db import get_db
from app.schemas.template import Template, TemplateCreate, TemplateUpdate
from app.repositories.template_repository import TemplateRepository
from app.commands.templates.create_template_command import CreateTemplateCommand
from app.commands.templates.update_template_command import UpdateTemplateCommand
from app.commands.templates.delete_template_command import DeleteTemplateCommand
from app.auth.rbac import build_rbac_dependencies
from app.routers.utils.dependencies import get_template_by_id, global_domain

router = APIRouter(
    prefix="/templates",
    tags=["templates"],
    responses={404: {"description": "Not found"}},
)

RESOURCE = "template"
rbac = build_rbac_dependencies(resource=RESOURCE, project_resolver=global_domain)


@router.post("", response_model=Template, status_code=status.HTTP_201_CREATED)
def create_template(
    request: TemplateCreate,
    db: Session = Depends(get_db),
    _authorized: bool = Depends(rbac["create"]),
) -> Template:
    return CreateTemplateCommand(db).execute(request)


@router.get("", response_model=Page[Template])
def list_templates(
    db: Session = Depends(get_db),
    params: Params = Depends(),
    _authorized: bool = Depends(rbac["read"]),
) -> Page[Template]:
    return paginate(TemplateRepository(db).get_templates_query(), params)


@router.get("/{template_id}", response_model=Template)
def get_template(
    template: Template = Depends(get_template_by_id),
    _authorized: bool = Depends(rbac["read"]),
) -> Template:
    return template


@router.patch("/{template_id}", response_model=Template)
def update_template(
    template_id: UUID,
    request: TemplateUpdate,
    db: Session = Depends(get_db),
    _authorized: bool = Depends(rbac["update"]),
) -> Template:
    result = UpdateTemplateCommand(db).execute(template_id, request)
    if result is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return result


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(
    template_id: UUID,
    db: Session = Depends(get_db),
    _authorized: bool = Depends(rbac["delete"]),
) -> None:
    deleted = DeleteTemplateCommand(db).execute(template_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Template not found")
