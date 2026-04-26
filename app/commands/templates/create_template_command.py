from sqlalchemy.orm import Session

from app.models.template import Template
from app.repositories.template_repository import TemplateRepository
from app.schemas.template import TemplateCreate


class CreateTemplateCommand:
    def __init__(self, db: Session):
        self.repo = TemplateRepository(db)

    def execute(self, req: TemplateCreate) -> Template:
        return self.repo.create_template(req)
