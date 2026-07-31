from typing import Optional
from uuid import UUID
from sqlalchemy.orm import Session

from app.models.layout import Layout
from app.repositories.layout_repository import LayoutRepository
from app.schemas.layout import LayoutCreate


class CreateLayoutCommand:
    def __init__(self, db: Session):
        self.repo = LayoutRepository(db)

    def execute(
        self, req: LayoutCreate, created_by_id: Optional[UUID] = None
    ) -> Layout:
        return self.repo.create_layout(req, created_by_id=created_by_id)
