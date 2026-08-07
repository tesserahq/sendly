"""Tests for PostmarkProvider: field mapping for send_email/send_batch,
MessageStream on both paths, mixed-outcome batch responses, and
SubscriptionChange normalization."""

from __future__ import annotations

from unittest.mock import patch

from app.providers.base import Attachment, EmailCreateRequest
from app.providers.postmark_provider import PostmarkProvider, _map_pm_type


def _make_request(**overrides):
    defaults = dict(
        from_email="sender@example.com",
        to=["user@example.com"],
        subject="Subject",
        html="<p>hi</p>",
        text="hi",
    )
    defaults.update(overrides)
    return EmailCreateRequest(**defaults)


class TestSendEmail:
    def test_maps_headers_attachments_and_message_stream(self):
        req = _make_request(
            custom_headers={"X-Custom": "value"},
            attachments=[
                Attachment(
                    filename="a.txt", content_bytes_b64="YWJj", mime_type="text/plain"
                )
            ],
            message_stream="broadcast-stream",
        )
        with patch("app.providers.postmark_provider.PostmarkClient") as MockClient:
            MockClient.return_value.emails.send.return_value = {
                "ErrorCode": 0,
                "MessageID": "pm-1",
            }
            provider = PostmarkProvider({})
            result = provider.send_email(req)

        call_kwargs = MockClient.return_value.emails.send.call_args.kwargs
        assert call_kwargs["Headers"] == [{"Name": "X-Custom", "Value": "value"}]
        assert call_kwargs["Attachments"] == [
            {"Name": "a.txt", "Content": "YWJj", "ContentType": "text/plain"}
        ]
        assert call_kwargs["MessageStream"] == "broadcast-stream"
        assert result.ok is True
        assert result.provider_message_id == "pm-1"

    def test_joins_multiple_recipients_with_comma(self):
        req = _make_request(to=["a@example.com", "b@example.com"])
        with patch("app.providers.postmark_provider.PostmarkClient") as MockClient:
            MockClient.return_value.emails.send.return_value = {
                "ErrorCode": 0,
                "MessageID": "pm-1",
            }
            PostmarkProvider({}).send_email(req)

        call_kwargs = MockClient.return_value.emails.send.call_args.kwargs
        assert call_kwargs["To"] == "a@example.com, b@example.com"

    def test_forwards_reply_to(self):
        req = _make_request(reply_to="reply@example.com")
        with patch("app.providers.postmark_provider.PostmarkClient") as MockClient:
            MockClient.return_value.emails.send.return_value = {
                "ErrorCode": 0,
                "MessageID": "pm-1",
            }
            PostmarkProvider({}).send_email(req)

        call_kwargs = MockClient.return_value.emails.send.call_args.kwargs
        assert call_kwargs["ReplyTo"] == "reply@example.com"

    def test_omits_reply_to_when_not_set(self):
        req = _make_request()
        with patch("app.providers.postmark_provider.PostmarkClient") as MockClient:
            MockClient.return_value.emails.send.return_value = {
                "ErrorCode": 0,
                "MessageID": "pm-1",
            }
            PostmarkProvider({}).send_email(req)

        call_kwargs = MockClient.return_value.emails.send.call_args.kwargs
        assert "ReplyTo" not in call_kwargs

    def test_omits_message_stream_when_not_set(self):
        req = _make_request()
        with patch("app.providers.postmark_provider.PostmarkClient") as MockClient:
            MockClient.return_value.emails.send.return_value = {
                "ErrorCode": 0,
                "MessageID": "pm-1",
            }
            PostmarkProvider({}).send_email(req)

        call_kwargs = MockClient.return_value.emails.send.call_args.kwargs
        assert "MessageStream" not in call_kwargs


class TestSendBatch:
    def test_maps_mixed_outcome_batch_response_in_order(self):
        requests = [
            _make_request(to=["ok@example.com"], message_stream="broadcast-stream"),
            _make_request(to=["bad@example.com"], message_stream="broadcast-stream"),
        ]
        with patch("app.providers.postmark_provider.PostmarkClient") as MockClient:
            MockClient.return_value.emails.send_batch.return_value = [
                {"ErrorCode": 0, "MessageID": "pm-ok"},
                {"ErrorCode": 300, "MessageID": None, "Message": "invalid email"},
            ]
            results = PostmarkProvider({}).send_batch(requests)

        assert results[0].ok is True
        assert results[0].provider_message_id == "pm-ok"
        assert results[1].ok is False
        assert results[1].error_code == "300"
        assert results[1].error_message == "invalid email"

        sent_messages = MockClient.return_value.emails.send_batch.call_args.args
        assert all(m["MessageStream"] == "broadcast-stream" for m in sent_messages)


class TestSubscriptionChangeMapping:
    def test_unsubscribe_maps_to_unsubscribed(self):
        assert (
            _map_pm_type("subscriptionchange", None, {"SuppressSending": True})
            == "unsubscribed"
        )

    def test_reactivation_maps_to_resubscribed(self):
        assert (
            _map_pm_type("subscriptionchange", None, {"SuppressSending": False})
            == "resubscribed"
        )

    def test_parse_webhook_preserves_full_payload(self):
        provider = PostmarkProvider({})
        payload = {
            "RecordType": "SubscriptionChange",
            "MessageID": "pm-123",
            "Recipient": "user@example.com",
            "ChangedAt": "2026-01-01T00:00:00Z",
            "SuppressSending": True,
            "Origin": "Recipient",
            "SuppressionReason": "HardBounce",
            "MessageStream": "broadcast",
        }
        events = list(provider.parse_webhook(payload, {}))
        assert len(events) == 1
        event = events[0]
        assert event.type == "unsubscribed"
        assert event.raw_payload == payload
