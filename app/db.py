from sqlalchemy import create_engine, event
from sqlalchemy.orm import (
    sessionmaker,
    declarative_base,
    with_loader_criteria,
    Session,
)
from app.config import get_settings
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

settings = get_settings()

engine = create_engine(
    settings.database_url,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
)

SQLAlchemyInstrumentor().instrument(
    enable_commenter=True, commenter_options={}, engine=engine
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
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


# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
