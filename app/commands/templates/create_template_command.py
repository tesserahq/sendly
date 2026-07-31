from typing import Optional
from uuid import UUID
from sqlalchemy.orm import Session

from app.models.template import Template
from app.repositories.template_repository import TemplateRepository
from app.schemas.template import TemplateCreate


class CreateTemplateCommand:
    def __init__(self, db: Session):
        self.repo = TemplateRepository(db)

    def execute(
        self, req: TemplateCreate, created_by_id: Optional[UUID] = None
    ) -> Template:
        return self.repo.create_template(req, created_by_id=created_by_id)
