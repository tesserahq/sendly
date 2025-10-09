import pytest
from uuid import uuid4
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate
from app.services.user_service import UserService


@pytest.fixture
def sample_user_data():
    return {
        "email": "test@example.com",
        "username": "testuser",
        "first_name": "Test",
        "last_name": "User",
        "provider": "google",
    }


@pytest.fixture
def sample_user(db: Session, sample_user_data):
    user = User(**sample_user_data)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_create_user(db: Session, sample_user_data):
    # Create user
    user_create = UserCreate(**sample_user_data)
    user = UserService(db).create_user(user_create)

    # Assertions
    assert user.id is not None
    assert user.email == sample_user_data["email"]
    assert user.username == sample_user_data["username"]
    assert user.first_name == sample_user_data["first_name"]
    assert user.last_name == sample_user_data["last_name"]
    assert (
        user.full_name()
        == f"{sample_user_data['first_name']} {sample_user_data['last_name']}"
    )
    assert user.provider == sample_user_data["provider"]
    assert user.verified is False
    assert user.verified_at is None
    assert user.created_at is not None
    assert user.updated_at is not None


def test_get_user(db: Session, sample_user):
    # Get user
    retrieved_user = UserService(db).get_user(sample_user.id)

    # Assertions
    assert retrieved_user is not None
    assert retrieved_user.id == sample_user.id
    assert retrieved_user.email == sample_user.email


def test_get_user_by_email(db: Session, sample_user):
    # Get user by email
    retrieved_user = UserService(db).get_user_by_email(sample_user.email)

    # Assertions
    assert retrieved_user is not None
    assert retrieved_user.id == sample_user.id
    assert retrieved_user.email == sample_user.email


def test_get_user_by_username(db: Session, sample_user):
    # Get user by username
    retrieved_user = UserService(db).get_user_by_username(sample_user.username)

    # Assertions
    assert retrieved_user is not None
    assert retrieved_user.id == sample_user.id
    assert retrieved_user.username == sample_user.username


def test_get_users(db: Session, sample_user):
    # Get all users
    users = UserService(db).get_users()

    # Assertions
    assert len(users) >= 1
    assert any(u.id == sample_user.id for u in users)


def test_update_user(db: Session, sample_user):
    # Update data
    update_data = {
        "email": "updated@example.com",
        "first_name": "Updated",
        "last_name": "Name",
    }
    user_update = UserUpdate(**update_data)

    # Update user
    updated_user = UserService(db).update_user(sample_user.id, user_update)

    # Assertions
    assert updated_user is not None
    assert updated_user.id == sample_user.id
    assert updated_user.email == update_data["email"]
    assert updated_user.first_name == update_data["first_name"]
    assert updated_user.last_name == update_data["last_name"]

    assert (
        updated_user.full_name()
        == f"{update_data['first_name']} {update_data['last_name']}"
    )


def test_verify_user(db: Session, sample_user):
    # Verify user
    verified_user = UserService(db).verify_user(sample_user.id)

    # Assertions
    assert verified_user is not None
    assert verified_user.verified is True
    assert verified_user.verified_at is not None
    assert isinstance(verified_user.verified_at, datetime)


def test_delete_user(db: Session, sample_user):
    user_service = UserService(db)
    # Delete user
    success = user_service.delete_user(sample_user.id)

    # Assertions
    assert success is True
    deleted_user = user_service.get_user(sample_user.id)
    assert deleted_user is None


def test_user_not_found_cases(db: Session):
    user_service = UserService(db)
    # Test various not found cases
    non_existent_id = uuid4()

    # Get non-existent user
    assert user_service.get_user(non_existent_id) is None

    # Get by non-existent email
    assert user_service.get_user_by_email("nonexistent@example.com") is None

    # Get by non-existent username
    assert user_service.get_user_by_username("nonexistent") is None

    # Update non-existent user
    update_data = {"email": "updated@example.com"}
    user_update = UserUpdate(**update_data)
    assert user_service.update_user(non_existent_id, user_update) is None

    # Delete non-existent user
    assert user_service.delete_user(non_existent_id) is False


# Test search method with dynamic filters
def test_search_users_with_filters(db: Session, sample_user):
    # Search using ilike filter on first name
    filters = {"first_name": {"operator": "ilike", "value": "%test%"}}
    results = UserService(db).search(filters)

    assert isinstance(results, list)
    assert any(user.id == sample_user.id for user in results)

    # Search using exact match
    filters = {"email": sample_user.email}
    results = UserService(db).search(filters)

    assert len(results) == 1
    assert results[0].id == sample_user.id

    # Search with no match
    filters = {"username": {"operator": "==", "value": "nonexistentuser"}}
    results = UserService(db).search(filters)

    assert len(results) == 0
