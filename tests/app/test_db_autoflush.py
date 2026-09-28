"""Production sessions autoflush (SQLAlchemy's default), so a query sees the
pending changes made earlier in the same execution without explicit flushes."""

import pytest

from app.db import SessionLocal, session_scope
from app.models.layout import Layout
from app.repositories.layout_repository import LayoutRepository


@pytest.fixture
def production_session(engine):
    """A session built by the production sessionmaker (not the test
    fixture's own), inside a rolled-back outer transaction."""
    connection = engine.connect()
    transaction = connection.begin()
    session = SessionLocal(bind=connection, join_transaction_mode="create_savepoint")
    yield session
    session.close()
    transaction.rollback()
    connection.close()


def test_managed_sessions_autoflush():
    with session_scope() as session:
        assert session.autoflush is True


def test_soft_delete_is_visible_to_the_next_query_without_flush(
    production_session, faker
):
    layout = Layout(alias=faker.slug(), name=faker.word(), html="<p>${content}</p>")
    production_session.add(layout)
    production_session.flush()
    repository = LayoutRepository(production_session)

    assert repository.delete_layout(layout.id) is True

    assert repository.get_layout(layout.id) is None
    assert layout.id not in {row.id for row in repository.get_layouts(limit=1000)}


def test_hard_delete_is_visible_to_the_next_query_without_flush(
    production_session, faker
):
    layout = Layout(alias=faker.slug(), name=faker.word(), html="<p>${content}</p>")
    production_session.add(layout)
    production_session.flush()
    repository = LayoutRepository(production_session)

    assert repository.hard_delete_record(layout.id) is True

    assert (
        production_session.query(Layout)
        .execution_options(skip_soft_delete_filter=True)
        .filter(Layout.id == layout.id)
        .first()
        is None
    )
