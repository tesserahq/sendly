import os
import sys

from app.core.celery_app import celery_app


def main():
    loglevel = os.getenv("CELERY_LOGLEVEL", "info")
    # macOS often hits fork-related segfaults with the default prefork pool
    default_pool = "solo" if sys.platform == "darwin" else "prefork"
    pool = os.getenv("CELERY_POOL", default_pool)
    concurrency = os.getenv("CELERY_CONCURRENCY", "1" if pool == "solo" else "4")
    queues = os.getenv("CELERY_QUEUES", "sendly")  # Default to sendly queue

    argv = [
        "worker",
        f"--loglevel={loglevel}",
        f"--pool={pool}",
        f"--concurrency={concurrency}",
        f"--queues={queues}",  # Always specify queues
    ]
    celery_app.worker_main(argv)


if __name__ == "__main__":
    main()
