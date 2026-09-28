from typing import Any, TypeVar

from sqlalchemy.engine import Result
from sqlalchemy.orm import Session
from sqlalchemy.sql import Executable

ScalarT = TypeVar("ScalarT")


class Repository:
    """Shared persistence mechanics for repositories.

    Set-based ORM UPDATE and DELETE statements bypass normal attribute assignment,
    so SQLAlchemy must reconcile their effects with objects already loaded in the
    Session identity map. All repository set-based mutations go through the two
    helpers below to make that behavior automatic.

    ``synchronize_session="fetch"`` makes SQLAlchemy identify the rows affected by
    the statement, using ``RETURNING`` when the database supports it or a SELECT
    otherwise. Matching objects already loaded by this Session are then refreshed
    or expired as appropriate. This prevents callers from observing stale Python
    objects after an atomic database update. We intentionally do not expose this
    option to individual repositories: disabling synchronization is an unsafe
    application-level optimization and previously required broad ``expire_all()``
    calls to repair the identity map.

    These helpers execute the supplied statement immediately and may trigger the
    Session's normal autoflush of pending ORM changes. They never commit, roll back,
    close the Session, or explicitly flush unrelated work; transaction ownership
    remains with the request or task Unit of Work.
    """

    _MUTATION_OPTIONS = {"synchronize_session": "fetch"}

    def __init__(self, db: Session):
        self.db = db

    def _execute_mutation(self, statement: Executable) -> Result[Any]:
        """Execute synchronized set-based ORM DML and return its full result."""
        return self.db.execute(statement, execution_options=self._MUTATION_OPTIONS)

    def _scalar_mutation(self, statement: Executable) -> ScalarT | None:
        """Execute synchronized ORM DML and return its first RETURNING value."""
        return self.db.scalar(statement, execution_options=self._MUTATION_OPTIONS)
