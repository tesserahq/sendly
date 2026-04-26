from uuid import UUID
from sqlalchemy.orm import Session

from app.models.layout import Layout
from app.repositories.layout_repository import LayoutRepository
from app.schemas.layout import LayoutUpdate


class UpdateLayoutCommand:
    def __init__(self, db: Session):
        self.repo = LayoutRepository(db)

    def execute(self, layout_id: UUID, req: LayoutUpdate) -> Layout:
        return self.repo.update_layout(layout_id, req)
