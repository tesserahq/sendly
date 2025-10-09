# Import celery app first
from app.core.celery_app import celery_app

# Initialize logging configuration for Celery workers
from app.core.logging_config import LoggingConfig

LoggingConfig()  # Initialize logging

# Import all models to ensure SQLAlchemy relationships are properly initialized
# This must be done before any database operations to avoid KeyError on model relationships
import app.models  # noqa: F401


# Import tasks for autodiscovery (using lazy imports to avoid heavy dependencies)
def _import_tasks():
    """Import tasks for registration."""
    # try:
    #     from . import backfill_digests  # noqa: F401
    # except ImportError:
    #     pass


_import_tasks()

__all__ = ["celery_app"]
