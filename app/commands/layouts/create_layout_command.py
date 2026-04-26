from sqlalchemy.orm import Session

from app.models.layout import Layout
from app.repositories.layout_repository import LayoutRepository
from app.schemas.layout import LayoutCreate


class CreateLayoutCommand:
    def __init__(self, db: Session):
        self.repo = LayoutRepository(db)

    def execute(self, req: LayoutCreate) -> Layout:
        return self.repo.create_layout(req)
