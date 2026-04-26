from uuid import UUID
from sqlalchemy.orm import Session

from app.repositories.template_repository import TemplateRepository


class DeleteTemplateCommand:
    def __init__(self, db: Session):
        self.repo = TemplateRepository(db)

    def execute(self, template_id: UUID) -> bool:
        return self.repo.delete_template(template_id)
