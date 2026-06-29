from uuid import UUID
from sqlalchemy.orm import Session

from app.exceptions.conflict_error import ConflictError
from app.exceptions.resource_not_found_error import ResourceNotFoundError
from app.models.template import Template
from app.repositories.template_repository import TemplateRepository
from app.schemas.template import TemplateClone, TemplateCreate


class CloneTemplateCommand:
    def __init__(self, db: Session):
        self.repo = TemplateRepository(db)

    def execute(self, template_id: UUID, req: TemplateClone) -> Template:
        source = self.repo.get_template(template_id)
        if source is None:
            raise ResourceNotFoundError("Template not found")

        new_alias = req.alias if req.alias is not None else f"{source.alias}-copy"
        new_name = (
            req.name
            if req.name is not None
            else (f"{source.name} copy" if source.name else None)
        )

        if self.repo.get_template_by_alias(new_alias) is not None:
            raise ConflictError(f"Template with alias '{new_alias}' already exists")

        clone_data = TemplateCreate(
            alias=new_alias,
            name=new_name,
            subject=source.subject,
            html=source.html,
            from_email=source.from_email,
            reply_to=source.reply_to,
            layout_id=source.layout_id,
        )
        return self.repo.create_template(clone_data)
