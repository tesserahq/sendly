"""NATS event builders for Email-related occurrences.

Follows the same CloudEvents-via-tessera_sdk shape used by sibling TesseraHQ
services (e.g. identies's app/events/client_events.py): a dotted event_type
constant, a build_*_event(...) function, and a subject that is a REST-style
resource path (used for CloudEvents metadata only — the actual NATS subject
passed to publish_sync is the event's event_type, not this field).
"""

from __future__ import annotations

from tessera_sdk.infra.events import Event, event_source, event_type

from app.models.email import Email

EMAIL_UNSUBSCRIBED = "email.unsubscribed"


def build_email_unsubscribed_event(email: Email) -> Event:
    return Event(
        source=event_source(),
        event_type=event_type(EMAIL_UNSUBSCRIBED),
        event_data={
            "id": str(email.id),
            "project_id": str(email.project_id) if email.project_id else None,
            "to_email": email.to_email,
            "batch_id": email.batch_id,
            "tags": email.tags,
            "metadata": email.metadata_,
        },
        subject=f"/emails/{email.id}",
        project_id=email.project_id,
        labels={
            "project_id": str(email.project_id) if email.project_id else None,
            "batch_id": email.batch_id,
        },
        tags=[
            tag
            for tag in [
                f"project_id:{email.project_id}" if email.project_id else None,
                f"batch_id:{email.batch_id}" if email.batch_id else None,
            ]
            if tag
        ],
    )
