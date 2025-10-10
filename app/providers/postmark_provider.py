# sendly/providers/postmark.py
from __future__ import annotations
from typing import Any, Dict, Iterable
from datetime import datetime, timezone
from .base import (
    EmailSendRequest,
    EmailSendResult,
    EmailEvent,
)
from postmarker.core import PostmarkClient
from app.providers.email_provider import EmailProvider


class PostmarkProvider(EmailProvider):
    def send_email(self, req: EmailSendRequest) -> EmailSendResult:
        settings = self.settings

        postmark = PostmarkClient(server_token=settings["api_key"])
        result = postmark.emails.send(
            From=req.from_email,
            # Check if postmark support sending to multiple recipients
            To=req.personalization.to[0],
            Subject=req.subject,
            HtmlBody=req.html,
            TextBody=req.text,
        )

        return EmailSendResult(
            ok=result["ErrorCode"] == 0,
            provider_message_id=result["MessageID"],
        )

    def verify_webhook(self, payload: bytes, headers: Dict[str, str]) -> bool:
        # Implement HMAC signature verification if enabled.
        return True

    def parse_webhook(
        self, payload: Dict[str, Any], headers: Dict[str, str]
    ) -> Iterable[EmailEvent]:
        # Postmark posts single-event JSON with "RecordType"
        # RecordType: Delivery, Bounce, SpamComplaint, Open, Click, SubscriptionChange, etc.
        record_type = payload.get("RecordType", "").lower()
        msg_id = payload.get("MessageID") or payload.get("MessageId") or ""
        ts = (
            payload.get("ReceivedAt")
            or payload.get("DeliveredAt")
            or payload.get("BouncedAt")
            or payload.get("Timestamp")
        )
        try:
            # Postmark timestamps are ISO8601
            occurred = (
                datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if ts
                else datetime.now(timezone.utc)
            )
        except Exception:
            occurred = datetime.now(timezone.utc)

        yield EmailEvent(
            tenant_id="__resolve_from_routing__",
            provider_name="postmark",
            provider_message_id=str(msg_id),
            type=_map_pm_type(record_type, payload.get("Type")),
            occurred_at=occurred,
            raw_payload=payload,
        )


def _map_pm_type(record_type: str, sub_type: str | None) -> str:
    if record_type == "delivery":
        return "delivered"
    if record_type == "open":
        return "opened"
    if record_type == "click":
        return "clicked"
    if record_type == "bounce":
        return "bounced"
    if record_type == "spamcomplaint":
        return "complained"
    # fallback
    return record_type or (sub_type or "unknown")
