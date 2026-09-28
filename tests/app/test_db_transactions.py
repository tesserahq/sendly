from contextlib import contextmanager
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.db import DbSession, on_commit, savepoint


def make_session() -> Session:
    return Session(create_engine("sqlite://"))


def test_on_commit_runs_callbacks_in_registration_order():
    session = make_session()
    calls = []

    on_commit(lambda: calls.append("first"), session=session)
    on_commit(lambda: calls.append("second"), session=session)
    session.execute(text("SELECT 1"))
    session.commit()

    assert calls == ["first", "second"]


def test_root_rollback_discards_on_commit_callbacks():
    session = make_session()
    calls = []

    on_commit(lambda: calls.append("called"), session=session)
    session.execute(text("SELECT 1"))
    session.rollback()
    session.commit()

    assert calls == []


def test_failed_savepoint_discards_only_its_callbacks():
    session = make_session()
    calls = []
    on_commit(lambda: calls.append("outer"), session=session)

    try:
        with savepoint(session):
            on_commit(lambda: calls.append("inner"), session=session)
            raise ValueError("invalid item")
    except ValueError:
        pass

    session.commit()

    assert calls == ["outer"]


def test_callback_failure_does_not_stop_later_callbacks():
    session = make_session()
    calls = []

    def fail():
        raise RuntimeError("callback failed")

    on_commit(fail, session=session)
    on_commit(lambda: calls.append("after failure"), session=session)
    session.execute(text("SELECT 1"))
    session.commit()

    assert calls == ["after failure"]


def test_http_commit_failure_is_reported_before_response_is_sent():
    app = FastAPI()

    @app.post("/write")
    def write(_session: DbSession):
        return {"status": "accepted"}

    @contextmanager
    def failing_scope():
        session = make_session()
        try:
            yield session
            raise RuntimeError("commit failed")
        finally:
            session.close()

    with patch("app.db.db_manager.db_session", failing_scope):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/write")

    assert response.status_code == 500
