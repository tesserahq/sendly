import pytest
from uuid import uuid4
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.email import Email
from app.models.email_event import EmailEvent
from app.schemas.email import (
    EmailCreate,
    EmailUpdate,
    EmailEventCreate,
    EmailEventUpdate,
)
from app.services.email_service import EmailService

# ==================== Email Fixtures ====================


@pytest.fixture
def sample_email_data(setup_tenant, setup_provider):
    """Sample email data for testing."""
    return {
        "from_email": "sender@example.com",
        "to_email": "recipient@example.com",
        "subject": "Test Email",
        "body": "This is a test email body.",
        "status": "pending",
        "provider_id": setup_provider.id,
        "tenant_id": setup_tenant.id,
    }


@pytest.fixture
def sample_email(db: Session, sample_email_data):
    """Create a sample email in the database."""
    email = Email(**sample_email_data)
    db.add(email)
    db.commit()
    db.refresh(email)
    return email


@pytest.fixture
def sample_email_event_data(sample_email):
    """Sample email event data for testing."""
    return {
        "email_id": sample_email.id,
        "event_type": "sent",
        "event_timestamp": datetime.now(timezone.utc),
        "details": {"message_id": "msg-12345", "response": "Email sent successfully"},
    }


@pytest.fixture
def sample_email_event(db: Session, sample_email_event_data):
    """Create a sample email event in the database."""
    event = EmailEvent(**sample_email_event_data)
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


# ==================== Email Tests ====================


def test_create_email(db: Session, sample_email_data):
    """Test creating a new email."""
    # Create email
    email_create = EmailCreate(**sample_email_data)
    email = EmailService(db).create_email(email_create)

    # Assertions
    assert email.id is not None
    assert email.from_email == sample_email_data["from_email"]
    assert email.to_email == sample_email_data["to_email"]
    assert email.subject == sample_email_data["subject"]
    assert email.body == sample_email_data["body"]
    assert email.status == sample_email_data["status"]
    assert email.provider_id == sample_email_data["provider_id"]
    assert email.tenant_id == sample_email_data["tenant_id"]
    assert email.sent_at is None
    assert email.error_message is None
    assert email.created_at is not None
    assert email.updated_at is not None


def test_get_email(db: Session, sample_email):
    """Test getting an email by ID."""
    # Get email
    retrieved_email = EmailService(db).get_email(sample_email.id)

    # Assertions
    assert retrieved_email is not None
    assert retrieved_email.id == sample_email.id
    assert retrieved_email.from_email == sample_email.from_email
    assert retrieved_email.to_email == sample_email.to_email


def test_get_emails(db: Session, sample_email):
    """Test getting a list of emails."""
    # Get all emails
    emails = EmailService(db).get_emails()

    # Assertions
    assert len(emails) >= 1
    assert any(e.id == sample_email.id for e in emails)


def test_get_emails_with_pagination(db: Session, setup_tenant, setup_provider):
    """Test getting emails with pagination."""
    email_service = EmailService(db)

    # Create additional emails
    for i in range(5):
        email_create = EmailCreate(
            from_email=f"sender{i}@example.com",
            to_email=f"recipient{i}@example.com",
            subject=f"Test Email {i}",
            body=f"Body {i}",
            status="pending",
            provider_id=setup_provider.id,
            tenant_id=setup_tenant.id,
        )
        email_service.create_email(email_create)

    # Test pagination
    first_page = email_service.get_emails(skip=0, limit=2)
    second_page = email_service.get_emails(skip=2, limit=2)

    # Assertions
    assert len(first_page) == 2
    assert len(second_page) == 2
    assert first_page[0].id != second_page[0].id


def test_get_emails_by_tenant(
    db: Session, setup_tenant, setup_another_tenant, setup_provider
):
    """Test getting emails for a specific tenant."""
    email_service = EmailService(db)

    # Create emails for the first tenant
    for i in range(3):
        email_create = EmailCreate(
            from_email=f"sender{i}@example.com",
            to_email=f"recipient{i}@example.com",
            subject=f"Tenant 1 Email {i}",
            body=f"Body {i}",
            status="pending",
            provider_id=setup_provider.id,
            tenant_id=setup_tenant.id,
        )
        email_service.create_email(email_create)

    # Create emails for the second tenant
    for i in range(2):
        email_create = EmailCreate(
            from_email=f"sender{i}@example.com",
            to_email=f"recipient{i}@example.com",
            subject=f"Tenant 2 Email {i}",
            body=f"Body {i}",
            status="pending",
            provider_id=setup_provider.id,
            tenant_id=setup_another_tenant.id,
        )
        email_service.create_email(email_create)

    # Get emails for each tenant
    tenant1_emails = email_service.get_emails_by_tenant(setup_tenant.id)
    tenant2_emails = email_service.get_emails_by_tenant(setup_another_tenant.id)

    # Assertions
    assert len(tenant1_emails) == 3
    assert len(tenant2_emails) == 2
    assert all(e.tenant_id == setup_tenant.id for e in tenant1_emails)
    assert all(e.tenant_id == setup_another_tenant.id for e in tenant2_emails)


def test_get_emails_by_provider(
    db: Session, setup_provider, setup_another_provider, setup_tenant
):
    """Test getting emails sent through a specific provider."""
    email_service = EmailService(db)

    # Create emails for the first provider
    for i in range(3):
        email_create = EmailCreate(
            from_email=f"sender{i}@example.com",
            to_email=f"recipient{i}@example.com",
            subject=f"Provider 1 Email {i}",
            body=f"Body {i}",
            status="sent",
            provider_id=setup_provider.id,
            tenant_id=setup_tenant.id,
        )
        email_service.create_email(email_create)

    # Create emails for the second provider
    for i in range(2):
        email_create = EmailCreate(
            from_email=f"sender{i}@example.com",
            to_email=f"recipient{i}@example.com",
            subject=f"Provider 2 Email {i}",
            body=f"Body {i}",
            status="sent",
            provider_id=setup_another_provider.id,
            tenant_id=setup_tenant.id,
        )
        email_service.create_email(email_create)

    # Get emails for each provider
    provider1_emails = email_service.get_emails_by_provider(setup_provider.id)
    provider2_emails = email_service.get_emails_by_provider(setup_another_provider.id)

    # Assertions
    assert len(provider1_emails) == 3
    assert len(provider2_emails) == 2
    assert all(e.provider_id == setup_provider.id for e in provider1_emails)
    assert all(e.provider_id == setup_another_provider.id for e in provider2_emails)


def test_get_emails_by_status(db: Session, setup_tenant, setup_provider):
    """Test getting emails with a specific status."""
    email_service = EmailService(db)

    # Create emails with different statuses
    for status in ["pending", "sent", "delivered", "failed"]:
        for i in range(2):
            email_create = EmailCreate(
                from_email=f"{status}{i}@example.com",
                to_email=f"recipient{i}@example.com",
                subject=f"{status.capitalize()} Email {i}",
                body=f"Body {i}",
                status=status,
                provider_id=setup_provider.id,
                tenant_id=setup_tenant.id,
            )
            email_service.create_email(email_create)

    # Get emails by status
    pending_emails = email_service.get_emails_by_status("pending")
    sent_emails = email_service.get_emails_by_status("sent")
    delivered_emails = email_service.get_emails_by_status("delivered")
    failed_emails = email_service.get_emails_by_status("failed")

    # Assertions
    assert len(pending_emails) == 2
    assert len(sent_emails) == 2
    assert len(delivered_emails) == 2
    assert len(failed_emails) == 2
    assert all(e.status == "pending" for e in pending_emails)
    assert all(e.status == "sent" for e in sent_emails)


def test_update_email(db: Session, sample_email):
    """Test updating an email."""
    # Update data
    update_data = {
        "status": "sent",
        "sent_at": datetime.now(timezone.utc),
    }
    email_update = EmailUpdate(**update_data)

    # Update email
    updated_email = EmailService(db).update_email(sample_email.id, email_update)

    # Assertions
    assert updated_email is not None
    assert updated_email.id == sample_email.id
    assert updated_email.status == update_data["status"]
    assert updated_email.sent_at is not None


def test_update_email_with_error(db: Session, sample_email):
    """Test updating an email with error information."""
    # Update data
    update_data = {
        "status": "failed",
        "error_message": "Failed to send email: Connection timeout",
    }
    email_update = EmailUpdate(**update_data)

    # Update email
    updated_email = EmailService(db).update_email(sample_email.id, email_update)

    # Assertions
    assert updated_email is not None
    assert updated_email.status == "failed"
    assert updated_email.error_message == update_data["error_message"]


def test_delete_email(db: Session, sample_email):
    """Test soft deleting an email."""
    email_service = EmailService(db)

    # Delete email
    success = email_service.delete_email(sample_email.id)

    # Assertions
    assert success is True
    deleted_email = email_service.get_email(sample_email.id)
    assert deleted_email is None


def test_email_not_found_cases(db: Session, setup_provider, setup_tenant):
    """Test various not found cases."""
    email_service = EmailService(db)

    # Test various not found cases
    non_existent_id = uuid4()

    # Get non-existent email
    assert email_service.get_email(non_existent_id) is None

    # Update non-existent email
    update_data = {"status": "sent"}
    email_update = EmailUpdate(**update_data)
    assert email_service.update_email(non_existent_id, email_update) is None

    # Delete non-existent email
    assert email_service.delete_email(non_existent_id) is False


def test_search_emails_with_filters(db: Session, sample_email):
    """Test searching emails with dynamic filters."""
    # Search using exact match on status
    filters = {"status": "pending"}
    results = EmailService(db).search(filters)

    assert isinstance(results, list)
    assert any(email.id == sample_email.id for email in results)

    # Search using ilike on subject
    filters = {"subject": {"operator": "ilike", "value": "%Test%"}}
    results = EmailService(db).search(filters)

    assert isinstance(results, list)
    assert any(email.id == sample_email.id for email in results)


# ==================== Email Event Tests ====================


def test_create_email_event(db: Session, sample_email_event_data):
    """Test creating a new email event."""
    # Create email event
    event_create = EmailEventCreate(**sample_email_event_data)
    event = EmailService(db).create_email_event(event_create)

    # Assertions
    assert event.id is not None
    assert event.email_id == sample_email_event_data["email_id"]
    assert event.event_type == sample_email_event_data["event_type"]
    assert event.event_timestamp is not None
    assert event.details == sample_email_event_data["details"]
    assert event.created_at is not None
    assert event.updated_at is not None


def test_get_email_event(db: Session, sample_email_event):
    """Test getting an email event by ID."""
    # Get email event
    retrieved_event = EmailService(db).get_email_event(sample_email_event.id)

    # Assertions
    assert retrieved_event is not None
    assert retrieved_event.id == sample_email_event.id
    assert retrieved_event.email_id == sample_email_event.email_id
    assert retrieved_event.event_type == sample_email_event.event_type


def test_get_email_events(db: Session, sample_email):
    """Test getting all events for an email."""
    email_service = EmailService(db)

    # Create multiple events for the email
    event_types = ["sent", "delivered", "opened", "clicked"]
    for event_type in event_types:
        event_create = EmailEventCreate(
            email_id=sample_email.id,
            event_type=event_type,
            event_timestamp=datetime.now(timezone.utc),
            details={"event": event_type},
        )
        email_service.create_email_event(event_create)

    # Get all events
    events = email_service.get_email_events(sample_email.id)

    # Assertions
    assert len(events) == 4
    assert all(e.email_id == sample_email.id for e in events)
    retrieved_types = {e.event_type for e in events}
    assert retrieved_types == set(event_types)


def test_get_email_events_by_type(db: Session, sample_email):
    """Test getting events of a specific type for an email."""
    email_service = EmailService(db)

    # Create multiple events with different types
    for i in range(3):
        email_service.create_email_event(
            EmailEventCreate(
                email_id=sample_email.id,
                event_type="delivered",
                event_timestamp=datetime.now(timezone.utc),
                details={"delivery": i},
            )
        )

    for i in range(2):
        email_service.create_email_event(
            EmailEventCreate(
                email_id=sample_email.id,
                event_type="opened",
                event_timestamp=datetime.now(timezone.utc),
                details={"open": i},
            )
        )

    # Get events by type
    delivered_events = email_service.get_email_events_by_type(
        sample_email.id, "delivered"
    )
    opened_events = email_service.get_email_events_by_type(sample_email.id, "opened")

    # Assertions
    assert len(delivered_events) == 3
    assert len(opened_events) == 2
    assert all(e.event_type == "delivered" for e in delivered_events)
    assert all(e.event_type == "opened" for e in opened_events)


def test_update_email_event(db: Session, sample_email_event):
    """Test updating an email event."""
    # Update data
    new_timestamp = datetime.now(timezone.utc)
    update_data = {
        "event_type": "delivered",
        "event_timestamp": new_timestamp,
        "details": {"updated": True, "delivery_status": "successful"},
    }
    event_update = EmailEventUpdate(**update_data)

    # Update email event
    updated_event = EmailService(db).update_email_event(
        sample_email_event.id, event_update
    )

    # Assertions
    assert updated_event is not None
    assert updated_event.id == sample_email_event.id
    assert updated_event.event_type == update_data["event_type"]
    assert updated_event.details == update_data["details"]


def test_delete_email_event(db: Session, sample_email_event):
    """Test deleting an email event."""
    email_service = EmailService(db)

    # Delete email event
    success = email_service.delete_email_event(sample_email_event.id)

    # Assertions
    assert success is True
    deleted_event = email_service.get_email_event(sample_email_event.id)
    assert deleted_event is None


def test_email_event_not_found_cases(db: Session, sample_email):
    """Test various not found cases for email events."""
    email_service = EmailService(db)

    # Test various not found cases
    non_existent_id = uuid4()

    # Get non-existent email event
    assert email_service.get_email_event(non_existent_id) is None

    # Update non-existent email event
    update_data = {"event_type": "delivered"}
    event_update = EmailEventUpdate(**update_data)
    assert email_service.update_email_event(non_existent_id, event_update) is None

    # Delete non-existent email event
    assert email_service.delete_email_event(non_existent_id) is False


def test_search_email_events_with_filters(db: Session, sample_email):
    """Test searching email events with dynamic filters."""
    email_service = EmailService(db)

    # Create events with different types
    for event_type in ["sent", "delivered", "bounced"]:
        email_service.create_email_event(
            EmailEventCreate(
                email_id=sample_email.id,
                event_type=event_type,
                event_timestamp=datetime.now(timezone.utc),
                details={"type": event_type},
            )
        )

    # Search using exact match on event_type
    filters = {"event_type": "delivered"}
    results = email_service.search_email_events(filters)

    assert isinstance(results, list)
    assert len(results) >= 1
    assert all(e.event_type == "delivered" for e in results)

    # Search by email_id
    filters = {"email_id": sample_email.id}
    results = email_service.search_email_events(filters)

    assert isinstance(results, list)
    assert len(results) >= 3
    assert all(e.email_id == sample_email.id for e in results)
