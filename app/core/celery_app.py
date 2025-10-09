# pyright: reportMissingTypeStubs=false
from celery import Celery
from app.config import get_settings

settings = get_settings()

celery_app = Celery("sendly-worker")

celery_app.conf.update(
    broker_url=f"redis://{settings.redis_host}:{settings.redis_port}/0",
    result_backend=f"redis://{settings.redis_host}:{settings.redis_port}/0",
    task_default_queue="sendly",  # Use dedicated queue for sendly tasks
    task_routes={
        "app.tasks.*": {"queue": "sendly"},  # Route all app.tasks.* to sendly queue
    },
)

# Optional configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

celery_app.autodiscover_tasks(["app.tasks"])  # ensure tasks are registered explicitly

# # Explicitly register tasks to ensure they're available
# def register_tasks():
#     """Explicitly import tasks to ensure registration."""
#     try:
#         from app.tasks.process_import_items import process_import_items  # noqa: F401
#         from app.tasks.backfill_digests import backfill_digests_task  # noqa: F401
#         print(f"✅ Tasks registered: process_import_items, backfill_digests_task")
#     except ImportError as e:
#         print(f"⚠️  Warning: Could not import tasks: {e}")

# # Register tasks when this module is imported
# register_tasks()
