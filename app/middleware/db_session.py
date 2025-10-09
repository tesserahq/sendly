# TODO: Is this the way we want to do this?
from starlette.middleware.base import BaseHTTPMiddleware
from app.db import SessionLocal  # or wherever your SQLAlchemy Session is
import logging

logger = logging.getLogger(__name__)


class DBSessionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        db_session = SessionLocal()
        request.state.db_session = db_session

        try:
            response = await call_next(request)
            # Commit any pending transactions on successful request
            db_session.commit()
            return response
        except Exception as e:
            # Rollback any pending transactions on error
            try:
                db_session.rollback()
            except Exception as rollback_error:
                logger.error(f"Error during rollback: {rollback_error}")
            raise e
        finally:
            # Always close the session to prevent resource leaks
            try:
                db_session.close()
            except Exception as close_error:
                logger.error(f"Error closing database session: {close_error}")
