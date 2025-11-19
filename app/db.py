"""
Database setup module.

This module uses DatabaseManager internally but maintains backward compatibility
by exposing the same interface (engine, SessionLocal, Base, get_db).

To move to a common package, use DatabaseManager directly.
"""

from app.config import get_settings
from tessera_sdk.core.database_manager import DatabaseManager
from sqlalchemy.orm import declarative_base
from sqlalchemy import event
from sqlalchemy.orm import Session
from sqlalchemy.orm import with_loader_criteria

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
get_db = db_manager.get_db
