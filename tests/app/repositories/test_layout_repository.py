import pytest
from uuid import uuid4
from app.models.layout import Layout
from app.schemas.layout import LayoutCreate, LayoutUpdate
from app.repositories.layout_repository import LayoutRepository


@pytest.fixture
def sample_layout(db):
    layout = Layout(
        alias="test-layout",
        name="Test Layout",
        html="<html><body>${content}</body></html>",
    )
    db.add(layout)
    db.commit()
    db.refresh(layout)
    return layout


class TestLayoutRepository:
    def test_create_layout(self, db):
        repo = LayoutRepository(db)
        layout = repo.create_layout(
            LayoutCreate(alias="welcome-layout", html="<html>${content}</html>")
        )
        assert layout.id is not None
        assert layout.alias == "welcome-layout"

    def test_get_layout(self, db, sample_layout):
        repo = LayoutRepository(db)
        result = repo.get_layout(sample_layout.id)
        assert result is not None
        assert result.id == sample_layout.id

    def test_get_layout_not_found(self, db):
        repo = LayoutRepository(db)
        assert repo.get_layout(uuid4()) is None

    def test_get_layout_by_alias(self, db, sample_layout):
        repo = LayoutRepository(db)
        result = repo.get_layout_by_alias("test-layout")
        assert result is not None
        assert result.id == sample_layout.id

    def test_get_layout_by_alias_not_found(self, db):
        repo = LayoutRepository(db)
        assert repo.get_layout_by_alias("nonexistent") is None

    def test_update_layout(self, db, sample_layout):
        repo = LayoutRepository(db)
        updated = repo.update_layout(
            sample_layout.id, LayoutUpdate(name="Updated Name")
        )
        assert updated.name == "Updated Name"
        assert updated.alias == sample_layout.alias

    def test_update_layout_not_found(self, db):
        repo = LayoutRepository(db)
        result = repo.update_layout(uuid4(), LayoutUpdate(name="X"))
        assert result is None

    def test_delete_layout(self, db, sample_layout):
        repo = LayoutRepository(db)
        deleted = repo.delete_layout(sample_layout.id)
        assert deleted is True
        assert repo.get_layout(sample_layout.id) is None

    def test_alias_uniqueness(self, db, sample_layout):
        repo = LayoutRepository(db)
        with pytest.raises(Exception):
            repo.create_layout(
                LayoutCreate(alias="test-layout", html="<html>${content}</html>")
            )
