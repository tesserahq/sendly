import logging
import os
import sys
from typing import Optional
from app.config import get_settings


class LoggingConfig:
    _instance: Optional["LoggingConfig"] = None
    _initialized: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self._settings = get_settings()
            self._configure_logging()
            self._initialized = True

    def _is_celery_worker(self) -> bool:
        """Check if we're running in a Celery worker context."""
        # Check for various indicators of Celery worker
        celery_indicators = [
            "celery" in os.environ.get("PROCESS_NAME", "").lower(),
            any("celery" in arg.lower() for arg in sys.argv),
            "worker" in sys.argv,
            os.environ.get("CELERY_LOGLEVEL") is not None,
            any("run_worker" in arg for arg in sys.argv),
        ]

        is_celery = any(celery_indicators)

        # Debug logging to understand context
        if is_celery:
            print("DEBUG: Detected Celery worker context")
            print(f"DEBUG: sys.argv = {sys.argv}")
            print(f"DEBUG: PROCESS_NAME = {os.environ.get('PROCESS_NAME', 'None')}")

        return is_celery

    def _configure_logging(self):
        """Configure logging based on settings and runtime context."""
        log_level = getattr(logging, self._settings.log_level.upper())
        is_celery = self._is_celery_worker()

        print(
            f"DEBUG: Configuring logging with level {self._settings.log_level}, is_celery={is_celery}"
        )

        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(log_level)

        # Always ensure root logger has a handler - this is safe for both contexts
        if not root_logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            handler.setFormatter(formatter)
            root_logger.addHandler(handler)
            print("DEBUG: Added handler to root logger")

        # Configure specific loggers
        loggers = {
            "uvicorn": log_level,
            "app": log_level,
            "fastapi": log_level,
            "celery": log_level,
            "sendly": log_level,  # For general app logging
            # Set third-party loggers to higher levels
            "httpx": logging.WARNING,
            "httpcore": logging.WARNING,
            "openai": logging.WARNING,
            "urllib3": logging.WARNING,
            "sqlalchemy": logging.WARNING,
            "llama_index": logging.WARNING,
        }

        for logger_name, level in loggers.items():
            logger = logging.getLogger(logger_name)
            logger.setLevel(level)

            # Always allow propagation for our app loggers to ensure visibility
            if logger_name in ["sendly", "app", "celery"]:
                logger.propagate = True
                print(f"DEBUG: Set {logger_name} logger propagate=True")
            else:
                # For web servers, prevent propagation to avoid duplicate logs
                if is_celery:
                    logger.propagate = True
                else:
                    logger.propagate = False
                    # Add handler if none exists (for web context)
                    if not logger.handlers:
                        handler = logging.StreamHandler()
                        formatter = logging.Formatter(
                            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
                        )
                        handler.setFormatter(formatter)
                        logger.addHandler(handler)

    @property
    def logger(self) -> logging.Logger:
        """Get a logger instance with the configured settings."""
        return logging.getLogger("sendly")

    def get_logger(self, name: str) -> logging.Logger:
        """Get a logger instance with the given name."""
        return logging.getLogger(name)


def get_logger(name: str = "sendly") -> logging.Logger:
    """Get a logger instance with the given name."""
    return LoggingConfig().get_logger(name)
