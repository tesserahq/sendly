from app.config import get_settings
import pytest
import logging
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from fastapi import Request
from fastapi.security import HTTPAuthorizationCredentials
from app.db import get_db
from app.main import create_app
from starlette.middleware.base import BaseHTTPMiddleware
from alembic import command
from alembic.config import Config
from faker import Faker

pytest_plugins = [
    "tests.fixtures.user_fixtures",
    "tests.fixtures.provider_fixtures",
    "tests.fixtures.tenant_fixtures",
    "tests.fixtures.email_fixtures",
]

logger = logging.getLogger(__name__)
settings = get_settings()


def ensure_test_database():
    """Ensure the test database exists."""

    # Connect to default postgres database
    default_url = settings.database_url.replace("/sendly_test", "/postgres")
    engine = create_engine(default_url, isolation_level="AUTOCOMMIT")
    conn = engine.connect()

    logger.debug(f"Connected to PostgreSQL database: {default_url}")

    # Check if test database exists
    result = conn.execute(
        text("SELECT 1 FROM pg_database WHERE datname = 'sendly_test'")
    )
    if not result.scalar():
        logger.debug("Creating test database...")
        conn.execute(text("CREATE DATABASE sendly_test"))
    else:
        logger.debug("Test database already exists")

    conn.close()
    engine.dispose()


def drop_test_database():
    """Drop the test database."""
    # Connect to default postgres database (not the test database)
    default_url = settings.database_url.replace("/sendly_test", "/postgres")
    engine = create_engine(default_url, isolation_level="AUTOCOMMIT")
    conn = engine.connect()

    # Terminate all connections to the test database
    conn.execute(
        text(
            """
        SELECT pg_terminate_backend(pid) 
        FROM pg_stat_activity 
        WHERE datname = 'sendly_test' AND pid <> pg_backend_pid()
    """
        )
    )

    # Drop the test database
    conn.execute(text("DROP DATABASE IF EXISTS sendly_test"))
    conn.close()
    engine.dispose()


@pytest.fixture(scope="session")
def engine():
    # Ensure test database exists
    ensure_test_database()

    # Create PostgreSQL engine for testing
    engine = create_engine(settings.database_url)

    logger.debug("Running migrations...")

    # Set up alembic configuration for testing
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", settings.database_url)

    # Run migrations to create tables
    command.upgrade(alembic_cfg, "head")
    logger.debug("Migrations completed successfully")

    yield engine

    logger.debug("Dropping test database...")
    # Drop the entire test database
    drop_test_database()
    logger.debug("Test database dropped successfully")

    engine.dispose()


@pytest.fixture(scope="function")
def db(engine):
    # Create a new database session for each test
    connection = engine.connect()
    transaction = connection.begin()

    # bind an individual Session to the connection
    Session = sessionmaker(bind=connection)
    session = Session()

    yield session

    # Clean up after each test
    session.close()

    # rollback - everything that happened with the
    # Session above (including calls to commit())
    # is rolled back.
    transaction.rollback()

    # return connection to the Engine
    connection.close()


@pytest.fixture(scope="function")
def faker():
    """Create a Faker instance for generating test data."""
    return Faker()


@pytest.fixture(scope="function")
def auth_token():
    """Create a mock authorization token for testing."""
    return "mock_token"


def create_client_fixture(user_fixture_name):
    """Helper function to create client fixtures with different users."""

    @pytest.fixture(scope="function")
    def client_fixture(db, request):
        """Create a FastAPI test client with overridden database dependency and auth."""

        # Get the user from the specified fixture
        test_user = request.getfixturevalue(user_fixture_name)

        def override_get_db():
            try:
                yield db
            finally:
                pass  # Don't close the session here, it's handled by the db fixture

        # Create app with testing mode ON (no auth middleware)
        logger.debug("Creating app with testing mode ON")
        app = create_app(testing=True, auth_middleware=MockAuthenticationMiddleware)

        # Store the test user in the app state so it can be accessed by the mock dependency
        app.state.test_user = test_user

        # Override dependencies
        app.dependency_overrides[get_db] = override_get_db

        # Create test client with auth headers
        test_client = TestClient(app)

        # Add default authorization header to all requests
        test_client.headers.update({"Authorization": "Bearer mock_token"})

        yield test_client

        # Clean up
        delattr(app.state, "test_user")
        app.dependency_overrides.clear()  # Clear overrides after test

    return client_fixture


# Create client fixtures using the helper function
client = create_client_fixture("setup_user")
client_another_user = create_client_fixture("setup_another_user")
client_test_user = create_client_fixture("test_user")


class MockAuthenticationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # Inject a fake user directly into request.state
        request.state.user = getattr(request.app.state, "test_user", None)
        return await call_next(request)


def mock_verify_token_dependency(
    request: Request,
    token: HTTPAuthorizationCredentials = None,
    db_session=None,
):
    """Mock the verify_token_dependency to bypass JWT verification."""
    # Get the test user from the app state
    user = getattr(request.app.state, "test_user", None)
    logger.debug(f"mock_verify_token_dependency: {user}")
    if user is None:
        raise Exception("Test user not found in app state")
    request.state.user = user

    return user
