import pytest
from datetime import datetime, timezone
from app.models.email import Email
from app.models.email_event import EmailEvent


@pytest.fixture(scope="function")
def setup_email(db, faker):
    """Create a test email for use in tests."""
    email_data = {
        "from_email": faker.email(),
        "to_email": faker.email(),
        "subject": faker.sentence(),
        "body": faker.text(),
        "status": "pending",
        "provider": "postmark",
        "project_id": None,
    }

    email = Email(**email_data)
    db.add(email)
    db.commit()
    db.refresh(email)

    return email


@pytest.fixture(scope="function")
def setup_another_email(db, faker):
    """Create another test email for use in tests."""
    email_data = {
        "from_email": faker.email(),
        "to_email": faker.email(),
        "subject": faker.sentence(),
        "body": faker.text(),
        "status": "sent",
        "provider": "postmark",
        "project_id": None,
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
