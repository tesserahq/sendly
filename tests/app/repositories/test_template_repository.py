import pytest
from uuid import uuid4
from app.models.layout import Layout
from app.models.template import Template
from app.schemas.template import TemplateCreate, TemplateUpdate
from app.repositories.template_repository import TemplateRepository


@pytest.fixture
def sample_layout(db):
    layout = Layout(
        alias="base-layout",
        html="<html><body>${content}</body></html>",
    )
    db.add(layout)
    db.commit()
    db.refresh(layout)
    return layout


@pytest.fixture
def sample_template(db):
    template = Template(
        alias="welcome-email",
        subject="Welcome ${name}",
        html="<p>Hello ${name}</p>",
        from_email="noreply@example.com",
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


class TestTemplateRepository:
    def test_create_template(self, db):
        repo = TemplateRepository(db)
        template = repo.create_template(
            TemplateCreate(
                alias="new-template",
                subject="Hi ${name}",
                html="<p>${name}</p>",
            )
        )
        assert template.id is not None
        assert template.alias == "new-template"

    def test_get_template(self, db, sample_template):
        repo = TemplateRepository(db)
        result = repo.get_template(sample_template.id)
        assert result is not None
        assert result.id == sample_template.id

    def test_get_template_not_found(self, db):
        repo = TemplateRepository(db)
        assert repo.get_template(uuid4()) is None

    def test_get_template_by_alias(self, db, sample_template):
        repo = TemplateRepository(db)
        result = repo.get_template_by_alias("welcome-email")
        assert result is not None
        assert result.id == sample_template.id

    def test_get_template_by_alias_not_found(self, db):
        repo = TemplateRepository(db)
        assert repo.get_template_by_alias("nonexistent") is None

    def test_get_template_eager_loads_layout(self, db, sample_layout):
        template = Template(
            alias="with-layout",
            subject="Hi",
            html="<p>body</p>",
            layout_id=sample_layout.id,
        )
        db.add(template)
        db.commit()
        db.refresh(template)

        repo = TemplateRepository(db)
        result = repo.get_template(template.id)
        assert result.layout is not None
        assert result.layout.id == sample_layout.id

    def test_update_template(self, db, sample_template):
        repo = TemplateRepository(db)
        updated = repo.update_template(
            sample_template.id, TemplateUpdate(subject="New Subject")
        )
        assert updated.subject == "New Subject"
        assert updated.alias == sample_template.alias

    def test_update_template_not_found(self, db):
        repo = TemplateRepository(db)
        result = repo.update_template(uuid4(), TemplateUpdate(subject="X"))
        assert result is None

    def test_delete_template(self, db, sample_template):
        repo = TemplateRepository(db)
        deleted = repo.delete_template(sample_template.id)
        assert deleted is True
        assert repo.get_template(sample_template.id) is None

    def test_alias_uniqueness(self, db, sample_template):
        repo = TemplateRepository(db)
        with pytest.raises(Exception):
            repo.create_template(
                TemplateCreate(
                    alias="welcome-email",
                    subject="Hi",
                    html="<p>dupe</p>",
                )
            )
