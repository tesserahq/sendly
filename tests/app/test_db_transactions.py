"""Sendly's wiring of the tessera_sdk managed-transaction boundary.

The on_commit / savepoint / session_scope contracts are tested in the SDK;
these tests pin how Sendly exposes them.
"""

from contextlib import contextmanager
from unittest.mock import patch

import tessera_sdk.infra as sdk_infra
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import db as app_db
from app.db import DbSession


def test_app_db_exposes_the_sdk_helpers():
    assert app_db.on_commit is sdk_infra.on_commit
    assert app_db.savepoint is sdk_infra.savepoint
    assert app_db.session_scope == app_db.db_manager.session_scope


def test_http_commit_failure_is_reported_before_response_is_sent():
    app = FastAPI()

    @app.post("/write")
    def write(_session: DbSession):
        return {"status": "accepted"}

    @contextmanager
    def failing_scope():
        session = Session(create_engine("sqlite://"))
        try:
            yield session
            raise RuntimeError("commit failed")
        finally:
            session.close()

    with patch.object(app_db.db_manager, "db_session", failing_scope):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/write")

    assert response.status_code == 500
