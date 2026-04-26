from uuid import UUID
from sqlalchemy.orm import Session

from app.repositories.layout_repository import LayoutRepository


class DeleteLayoutCommand:
    def __init__(self, db: Session):
        self.repo = LayoutRepository(db)

    def execute(self, layout_id: UUID) -> bool:
        return self.repo.delete_layout(layout_id)
