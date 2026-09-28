"""Database setup and the application's transaction boundary.

Transaction handling comes from tessera_sdk (docs/managed-transactions.md in
tessera-sdk-py): each execution gets one session that commits on success and
rolls back on error. This module wires it to Sendly's settings and re-exports
the helpers under the names the application imports.
"""

from sqlalchemy import event
from sqlalchemy.orm import Session, declarative_base, with_loader_criteria
from tessera_sdk.infra import current_session, on_commit, savepoint
from tessera_sdk.infra.database import DatabaseManager
from tessera_sdk.server.dependencies import create_db_dependency

from app.config import get_settings

__all__ = [
    "Base",
    "DbSession",
    "SessionLocal",
    "current_session",
    "db_manager",
    "engine",
    "get_db",
    "on_commit",
    "savepoint",
    "session_scope",
]

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


settings = get_settings()
db_manager = DatabaseManager(
    database_url=settings.database_url,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    pool_pre_ping=True,
    pool_recycle=300,
    pool_use_lifo=True,
    application_name=settings.db_app_name,
    autoflush=True,
)

engine = db_manager.engine
SessionLocal = db_manager.SessionLocal

# One managed session per execution: routes declare `db: DbSession`; tasks and
# other entry points use `with session_scope() as db:`.
get_db, DbSession = create_db_dependency(db_manager)
session_scope = db_manager.session_scope
