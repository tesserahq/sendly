from typing import List, Optional
from uuid import UUID
from sqlalchemy.orm import Session

from app.models.layout import Layout
from app.repositories.soft_delete_repository import SoftDeleteRepository
from app.schemas.layout import LayoutCreate, LayoutUpdate


class LayoutRepository(SoftDeleteRepository[Layout]):
    def __init__(self, db: Session):
        super().__init__(db, Layout)

    def get_layout(self, layout_id: UUID) -> Optional[Layout]:
        return self.db.query(Layout).filter(Layout.id == layout_id).first()

    def get_layout_by_alias(self, alias: str) -> Optional[Layout]:
        return self.db.query(Layout).filter(Layout.alias == alias).first()

    def get_layouts_query(self):
        return self.db.query(Layout).order_by(Layout.created_at.desc())

    def get_layouts(self, skip: int = 0, limit: int = 100) -> List[Layout]:
        return self.db.query(Layout).offset(skip).limit(limit).all()

    def create_layout(self, layout: LayoutCreate) -> Layout:
        db_layout = Layout(**layout.model_dump())
        self.db.add(db_layout)
        self.db.commit()
        self.db.refresh(db_layout)
        return db_layout

    def update_layout(self, layout_id: UUID, layout: LayoutUpdate) -> Optional[Layout]:
        db_layout = self.db.query(Layout).filter(Layout.id == layout_id).first()
        if db_layout:
            for key, value in layout.model_dump(exclude_unset=True).items():
                setattr(db_layout, key, value)
            self.db.commit()
            self.db.refresh(db_layout)
        return db_layout

    def delete_layout(self, layout_id: UUID) -> bool:
        return self.delete_record(layout_id)
