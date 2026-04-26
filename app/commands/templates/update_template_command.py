from uuid import UUID
from sqlalchemy.orm import Session

from app.models.template import Template
from app.repositories.template_repository import TemplateRepository
from app.schemas.template import TemplateUpdate


class UpdateTemplateCommand:
    def __init__(self, db: Session):
        self.repo = TemplateRepository(db)

    def execute(self, template_id: UUID, req: TemplateUpdate) -> Template:
        return self.repo.update_template(template_id, req)
