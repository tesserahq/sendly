"""Database setup and the application's transaction boundary."""

import logging
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy import event
from sqlalchemy.orm import Session, declarative_base, with_loader_criteria
from tessera_sdk.infra.database import DatabaseManager

from app.config import get_settings

logger = logging.getLogger(__name__)

_ON_COMMIT_HOOKS = "sendly_on_commit_hooks"
_current_session: ContextVar[Session | None] = ContextVar(
    "sendly_current_session", default=None
)

Base = declarative_base()


@event.listens_for(Session, "do_orm_execute")
def _add_soft_delete_criteria(execute_state):
    """
    Automatically filter out soft-deleted records from all queries.
    """
    from app.models.mixins import SoftDeleteMixin

    skip_filter = execute_state.execution_options.get("skip_soft_delete_filter", False)
    if execute_state.is_select and not skip_filter:
        execute_state.statement = execute_state.statement.options(
            with_loader_criteria(
                SoftDeleteMixin,
                lambda cls: cls.deleted_at.is_(None),
                include_aliases=True,
            )
        )


# Initialize database manager
settings = get_settings()
db_manager = DatabaseManager(
    database_url=settings.database_url,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    pool_pre_ping=True,
    pool_recycle=300,
    pool_use_lifo=True,
    application_name=settings.db_app_name,
)

# Expose the same interface for backward compatibility
engine = db_manager.engine
SessionLocal = db_manager.SessionLocal


@contextmanager
def session_scope() -> Iterator[Session]:
    """Open one managed session for one application execution."""
    with db_manager.db_session() as session:
        token = _current_session.set(session)
        try:
            yield session
        finally:
            _current_session.reset(token)


async def get_db() -> AsyncIterator[Session]:
    """Commit or roll back before FastAPI sends the response."""
    with session_scope() as session:
        yield session


DbSession = Annotated[Session, Depends(get_db, scope="function")]


def on_commit(
    callback: Callable[[], Any], session: Session | None = None
) -> None:
    """Run ``callback`` after commit, or immediately outside a managed scope."""
    active_session = session or _current_session.get()
    if active_session is None:
        callback()
        return

    hooks = active_session.info.setdefault(_ON_COMMIT_HOOKS, [])
    hooks.append(callback)


@contextmanager
def savepoint(session: Session) -> Iterator[None]:
    """Create a savepoint and discard callbacks registered by failed work."""
    hooks = session.info.setdefault(_ON_COMMIT_HOOKS, [])
    mark = len(hooks)
    try:
        with session.begin_nested():
            yield
    except Exception:
        del hooks[mark:]
        raise


@event.listens_for(Session, "after_commit")
def _run_on_commit_hooks(session: Session) -> None:
    # Releasing a savepoint is not a durability boundary.
    if session.in_nested_transaction():
        return

    hooks = session.info.pop(_ON_COMMIT_HOOKS, [])
    for callback in hooks:
        try:
            callback()
        except Exception:
            logger.exception(
                "Post-commit callback failed",
                extra={"callback": getattr(callback, "__qualname__", repr(callback))},
            )


@event.listens_for(Session, "after_soft_rollback")
def _discard_on_root_rollback(session: Session, transaction) -> None:
    if transaction.parent is None:
        session.info.pop(_ON_COMMIT_HOOKS, None)
