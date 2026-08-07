from typing import List, Optional
from uuid import UUID
from sqlalchemy.orm import Session, selectinload

from app.models.template import Template
from app.repositories.soft_delete_repository import SoftDeleteRepository
from app.schemas.template import TemplateCreate, TemplateUpdate


class TemplateRepository(SoftDeleteRepository[Template]):
    def __init__(self, db: Session):
        super().__init__(db, Template)

    def get_template(self, template_id: UUID) -> Optional[Template]:
        return (
            self.db.query(Template)
            .options(selectinload(Template.layout), selectinload(Template.created_by))
            .filter(Template.id == template_id)
            .first()
        )

    def get_template_by_alias(self, alias: str) -> Optional[Template]:
        return (
            self.db.query(Template)
            .options(selectinload(Template.layout), selectinload(Template.created_by))
            .filter(Template.alias == alias)
            .first()
        )

    def get_templates_query(self, tags: Optional[List[str]] = None):
        query = (
            self.db.query(Template)
            .options(selectinload(Template.layout), selectinload(Template.created_by))
            .order_by(Template.created_at.desc())
        )
        if tags:
            query = query.filter(Template.tags.contains(tags))
        return query

    def get_unique_tags(self) -> List[str]:
        rows = self.db.query(Template.tags).filter(Template.tags.isnot(None)).all()
        unique_tags = set()
        for (tags,) in rows:
            if tags:
                unique_tags.update(tags)
        return sorted(unique_tags)

    def get_templates(self, skip: int = 0, limit: int = 100) -> List[Template]:
        return self.db.query(Template).offset(skip).limit(limit).all()

    def create_template(
        self, template: TemplateCreate, created_by_id: Optional[UUID] = None
    ) -> Template:
        db_template = Template(**template.model_dump(), created_by_id=created_by_id)
        self.db.add(db_template)
        self.db.commit()
        self.db.refresh(db_template)
        return db_template

    def update_template(
        self, template_id: UUID, template: TemplateUpdate
    ) -> Optional[Template]:
        db_template = self.db.query(Template).filter(Template.id == template_id).first()
        if db_template:
            for key, value in template.model_dump(exclude_unset=True).items():
                setattr(db_template, key, value)
            self.db.commit()
            self.db.refresh(db_template)
        return db_template

    def delete_template(self, template_id: UUID) -> bool:
        return self.delete_record(template_id)
