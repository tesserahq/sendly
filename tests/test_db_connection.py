import pytest
from sqlalchemy import text
from app.db import engine, SessionLocal


def test_database_connection():
    """Test if the database connection is working properly."""
    try:
        # Try to create a session and execute a simple query
        with SessionLocal() as session:
            # Execute a simple query to check connection
            result = session.execute(text("SELECT 1"))
            assert result.scalar() == 1
    except Exception as e:
        pytest.fail(f"Database connection failed: {str(e)}")


def test_database_connection_with_engine():
    """Test database connection using the engine directly."""
    try:
        # Try to connect using the engine
        with engine.connect() as connection:
            # Execute a simple query
            result = connection.execute(text("SELECT 1"))
            assert result.scalar() == 1
    except Exception as e:
        pytest.fail(f"Database connection failed: {str(e)}")
