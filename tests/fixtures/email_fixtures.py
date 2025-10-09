import pytest
from datetime import datetime, timezone
from app.models.email import Email
from app.models.email_event import EmailEvent


@pytest.fixture(scope="function")
def setup_email(db, setup_tenant, setup_provider, faker):
    """Create a test email for use in tests."""
    email_data = {
        "from_email": faker.email(),
        "to_email": faker.email(),
        "subject": faker.sentence(),
        "body": faker.text(),
        "status": "pending",
        "provider_id": setup_provider.id,
        "tenant_id": setup_tenant.id,
    }

    email = Email(**email_data)
    db.add(email)
    db.commit()
    db.refresh(email)

    return email


@pytest.fixture(scope="function")
def setup_another_email(db, setup_tenant, setup_provider, faker):
    """Create another test email for use in tests."""
    email_data = {
        "from_email": faker.email(),
        "to_email": faker.email(),
        "subject": faker.sentence(),
        "body": faker.text(),
        "status": "sent",
        "provider_id": setup_provider.id,
        "tenant_id": setup_tenant.id,
        "sent_at": datetime.now(timezone.utc),
    }

    email = Email(**email_data)
    db.add(email)
    db.commit()
    db.refresh(email)

    return email


@pytest.fixture(scope="function")
def setup_email_event(db, setup_email, faker):
    """Create a test email event for use in tests."""
    event_data = {
        "email_id": setup_email.id,
        "event_type": "sent",
        "event_timestamp": datetime.now(timezone.utc),
        "details": {
            "message_id": faker.uuid4(),
            "provider_response": "Email sent successfully",
        },
    }

    event = EmailEvent(**event_data)
    db.add(event)
    db.commit()
    db.refresh(event)

    return event
