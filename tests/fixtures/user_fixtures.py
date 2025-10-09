import pytest
from app.models.user import User


@pytest.fixture(scope="function")
def test_user(db, faker):
    """Create a test user for use in tests."""
    email = faker.email()

    user_data = {
        "email": email,
        "username": email,
        "first_name": faker.first_name(),
        "last_name": faker.last_name(),
        "provider": "google",
        "external_id": str(faker.uuid4()),
    }

    user = User(**user_data)
    db.add(user)
    db.commit()
    db.refresh(user)

    return user


@pytest.fixture(scope="function")
def setup_user(db, faker):
    """Create a test user for use in tests."""
    email = faker.email()

    user_data = {
        "email": email,
        "username": email,
        "first_name": faker.first_name(),
        "last_name": faker.last_name(),
        "provider": "google",
        "external_id": str(faker.uuid4()),
    }

    user = User(**user_data)
    db.add(user)
    db.commit()
    db.refresh(user)

    return user


@pytest.fixture(scope="function")
def setup_another_user(db, faker):
    """Create a test user for use in tests."""
    email = faker.email()

    user_data = {
        "email": email,
        "username": email,
        "first_name": faker.first_name(),
        "last_name": faker.last_name(),
        "provider": "google",
        "external_id": str(faker.uuid4()),
    }

    user = User(**user_data)
    db.add(user)
    db.commit()
    db.refresh(user)

    return user
