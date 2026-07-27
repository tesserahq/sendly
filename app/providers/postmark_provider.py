# sendly/providers/postmark.py
from __future__ import annotations
from typing import Any, Dict, Iterable, List, Optional
from datetime import datetime, timezone
from .base import (
    EmailCreateRequest,
    EmailSendResult,
    EmailEvent,
)
from postmarker.core import PostmarkClient
from postmarker.exceptions import ClientError
from app.providers.email_provider import EmailProvider
from app.providers.provider_errors import ProviderError
from app.config import get_settings


def _build_message(req: EmailCreateRequest) -> Dict[str, Any]:
    """Build the postmarker `emails.send`/`send_batch` kwargs for one request."""
    message: Dict[str, Any] = {
        "From": req.from_email,
        # Postmark's To accepts comma-separated addresses (max 50).
        "To": ", ".join(req.to),
        "Subject": req.subject,
        "HtmlBody": req.html,
        "TextBody": req.text,
        "TrackOpens": True,
    }
    if req.custom_headers:
        message["Headers"] = [
            {"Name": name, "Value": value} for name, value in req.custom_headers.items()
        ]
    if req.attachments:
        message["Attachments"] = [
            {
                "Name": attachment.filename,
                "Content": attachment.content_bytes_b64,
                "ContentType": attachment.mime_type,
            }
            for attachment in req.attachments
        ]
    if req.message_stream:
        message["MessageStream"] = req.message_stream
    return message


class PostmarkProvider(EmailProvider):
    provider_id = "postmark"
    provider_name = "Postmark"
    enabled = True
    default = True
    site = "https://postmarkapp.com"

    def send_email(self, req: EmailCreateRequest) -> EmailSendResult:
        settings = get_settings()

        postmark = PostmarkClient(server_token=settings.postmark_api_key)
        try:
            result = postmark.emails.send(**_build_message(req))
        except ClientError as e:
            raise ProviderError(str(e)) from e

        return EmailSendResult(
            ok=result["ErrorCode"] == 0,
            provider_message_id=result["MessageID"],
        )

    def send_batch(self, requests: List[EmailCreateRequest]) -> List[EmailSendResult]:
        settings = get_settings()

        postmark = PostmarkClient(server_token=settings.postmark_api_key)
        messages = [_build_message(req) for req in requests]
        try:
            results = postmark.emails.send_batch(*messages)
        except ClientError as e:
            raise ProviderError(str(e)) from e

        return [
            EmailSendResult(
                ok=result.get("ErrorCode") == 0,
                provider_message_id=result.get("MessageID"),
                error_code=(
                    None
                    if result.get("ErrorCode") == 0
                    else str(result.get("ErrorCode"))
                ),
                error_message=result.get("Message"),
            )
            for result in results
        ]

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
            or payload.get("ChangedAt")
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
            project_id=None,  # Will be resolved from the email record
            provider_name="postmark",
            provider_message_id=str(msg_id),
            type=_map_pm_type(record_type, payload.get("Type"), payload),
            occurred_at=occurred,
            raw_payload=payload,
        )


def _map_pm_type(
    record_type: str, sub_type: Optional[str], payload: Optional[Dict[str, Any]] = None
) -> str:
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
    if record_type == "subscriptionchange":
        # Not a blanket subscriptionchange -> unsubscribed mapping: SubscriptionChange
        # covers both an unsubscribe and a reactivation, distinguished by SuppressSending.
        suppress_sending = bool((payload or {}).get("SuppressSending"))
        return "unsubscribed" if suppress_sending else "resubscribed"
    # fallback
    return record_type or (sub_type or "unknown")
