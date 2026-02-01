"""Command for processing email delivery events from provider webhooks."""

from __future__ import annotations
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.providers.email_provider import EmailProvider
from app.providers.base import EmailEvent
from app.services.email_service import EmailService
from app.schemas.email import EmailEventCreate


class ProcessDeliveryEventsCommand:
    """
    Command to process webhook delivery events from email providers.

    This command handles:
    1. Webhook signature verification
    2. Parsing provider-specific webhook payloads
    3. Finding the associated email by provider_message_id
    4. Creating email event records in the database
    """

    def __init__(self, db: Session):
        """
        Initialize the command.

        Args:
            db: Database session
        """
        self.db = db
        self.email_service = EmailService(db)

    def execute(
        self,
        provider: EmailProvider,
        body_bytes: bytes,
        payload: Dict[str, Any],
        headers: Dict[str, str],
    ) -> Dict[str, Any]:
        """
        Process delivery events from a provider webhook.

        Args:
            provider: The email provider instance
            body_bytes: Raw request body bytes (for signature verification)
            payload: Parsed JSON payload
            headers: Request headers

        Returns:
            Dict with processing results including success count and failures

        Raises:
            HTTPException: If webhook verification fails
        """
        # Verify webhook signature
        if not provider.verify_webhook(body_bytes, headers):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Webhook signature verification failed",
            )

        # Parse webhook events
        parsed_events = list(provider.parse_webhook(payload, headers))

        # Process each event
        processed_count = 0
        failed_events: List[Dict[str, Any]] = []

        for event in parsed_events:
            try:
                self._process_single_event(event, provider.provider_id)
                processed_count += 1
            except Exception as e:
                failed_events.append(
                    {
                        "provider_message_id": event.provider_message_id,
                        "error": str(e),
                    }
                )

        return {
            "status": "success" if processed_count > 0 else "partial_failure",
            "provider": provider.provider_id,
            "events_received": len(parsed_events),
            "events_processed": processed_count,
            "events_failed": len(failed_events),
            "failures": failed_events if failed_events else None,
        }

    def _process_single_event(self, event: EmailEvent, provider_id: str) -> None:
        """
        Process a single email event.

        Args:
            event: The parsed email event
            provider_id: The provider identifier

        Raises:
            ValueError: If the email associated with the event cannot be found
        """
        # Find the email by provider_message_id
        email = self.email_service.get_email_by_provider_message_id(
            provider_message_id=event.provider_message_id,
            provider=provider_id,
        )

        if not email:
            raise ValueError(
                f"Email not found for provider_message_id: {event.provider_message_id}"
            )

        # Create the email event
        email_event = EmailEventCreate(
            email_id=email.id,
            event_type=event.type,
            event_timestamp=event.occurred_at,
            details=event.raw_payload,
        )

        self.email_service.create_email_event(email_event)
