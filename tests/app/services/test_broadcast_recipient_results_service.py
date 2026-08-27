"""Tests for BroadcastRecipientResultsService: the left join from broadcast
recipients to their resulting email, stable ordering, and result projection.
"""

from __future__ import annotations

from uuid import uuid4

from fastapi_pagination import Params

from app.constants.email import EmailStatus
from app.models.broadcast_batch import BroadcastBatch
from app.models.broadcast_recipient import BroadcastRecipient
from app.models.email import Email
from app.services.broadcast_recipient_results_service import (
    BroadcastRecipientResultsService,
)


def _make_batch(db, **overrides):
    defaults = dict(
        project_id=uuid4(),
        batch_id=str(uuid4()),
        content_spec={},
        queued_count=1,
        suppressed_count=0,
    )
    defaults.update(overrides)
    batch = BroadcastBatch(**defaults)
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch


def _make_email(db, project_id, to_email, **overrides):
    defaults = dict(
        project_id=project_id,
        from_email="sender@example.com",
        to_email=to_email,
        subject="Hi",
        body="Body",
        status=EmailStatus.SENT,
        provider="postmark",
    )
    defaults.update(overrides)
    email = Email(**defaults)
    db.add(email)
    db.commit()
    db.refresh(email)
    return email


def _make_recipient(db, batch, email_address, **overrides):
    defaults = dict(
        broadcast_batch_id=batch.id,
        email=email_address,
        suppressed=False,
        prepared=False,
    )
    defaults.update(overrides)
    recipient = BroadcastRecipient(**defaults)
    db.add(recipient)
    db.commit()
    db.refresh(recipient)
    return recipient


class TestBroadcastRecipientResultsService:
    def test_normal_prepared_recipient_includes_email_fields(self, db):
        batch = _make_batch(db)
        email = _make_email(db, batch.project_id, "a@example.com")
        _make_recipient(db, batch, "a@example.com", prepared=True, email_id=email.id)

        page = BroadcastRecipientResultsService(db).get_page(batch, Params())

        assert len(page.items) == 1
        item = page.items[0]
        assert item.email == "a@example.com"
        assert item.prepared is True
        assert item.suppressed is False
        assert item.email_id == email.id
        assert item.email_status == EmailStatus.SENT

    def test_suppressed_recipient_has_no_email(self, db):
        batch = _make_batch(db)
        _make_recipient(db, batch, "suppressed@example.com", suppressed=True)

        page = BroadcastRecipientResultsService(db).get_page(batch, Params())

        item = page.items[0]
        assert item.suppressed is True
        assert item.email_id is None
        assert item.email_status is None
        assert item.opened_at is None
        assert item.clicked_at is None

    def test_preparation_failure_has_prepared_true_no_email(self, db):
        """A rendering failure: prepare marks the recipient prepared, but no
        Email is ever created for it."""
        batch = _make_batch(db)
        _make_recipient(db, batch, "broken@example.com", prepared=True)

        page = BroadcastRecipientResultsService(db).get_page(batch, Params())

        item = page.items[0]
        assert item.prepared is True
        assert item.suppressed is False
        assert item.email_id is None

    def test_null_caller_reference_is_returned_as_none(self, db):
        batch = _make_batch(db)
        _make_recipient(db, batch, "a@example.com")

        page = BroadcastRecipientResultsService(db).get_page(batch, Params())

        assert page.items[0].client_reference_id is None

    def test_duplicate_email_addresses_distinguished_by_reference(self, db):
        batch = _make_batch(db)
        ref_a, ref_b = uuid4(), uuid4()
        email_a = _make_email(db, batch.project_id, "dup@example.com")
        email_b = _make_email(db, batch.project_id, "dup@example.com")
        _make_recipient(
            db,
            batch,
            "dup@example.com",
            client_reference_id=ref_a,
            prepared=True,
            email_id=email_a.id,
        )
        _make_recipient(
            db,
            batch,
            "dup@example.com",
            client_reference_id=ref_b,
            prepared=True,
            email_id=email_b.id,
        )

        page = BroadcastRecipientResultsService(db).get_page(batch, Params())

        by_ref = {item.client_reference_id: item for item in page.items}
        assert len(by_ref) == 2
        assert by_ref[ref_a].email_id == email_a.id
        assert by_ref[ref_b].email_id == email_b.id

    def test_historical_row_without_email_relationship_is_visible(self, db):
        """Pre-migration recipients have no email_id even if a same-address
        Email row exists elsewhere — the query never infers the link by
        matching addresses."""
        batch = _make_batch(db)
        _make_email(db, batch.project_id, "legacy@example.com")
        _make_recipient(db, batch, "legacy@example.com", prepared=True)

        page = BroadcastRecipientResultsService(db).get_page(batch, Params())

        item = page.items[0]
        assert item.email_id is None
        assert item.email_status is None

    def test_ordering_is_stable_by_created_at_then_id(self, db):
        batch = _make_batch(db)
        for i in range(5):
            _make_recipient(db, batch, f"user{i}@example.com")

        page = BroadcastRecipientResultsService(db).get_page(
            batch, Params(page=1, size=100)
        )

        emails = [item.email for item in page.items]
        assert emails == sorted(emails, key=lambda e: e)  # inserted in order

    def test_total_count_reflects_full_recipient_count(self, db):
        batch = _make_batch(db)
        for i in range(3):
            _make_recipient(db, batch, f"user{i}@example.com")

        page = BroadcastRecipientResultsService(db).get_page(
            batch, Params(page=1, size=2)
        )

        assert page.total == 3
        assert len(page.items) == 2

    def test_results_scoped_to_one_batch(self, db):
        batch_one = _make_batch(db)
        batch_two = _make_batch(db)
        _make_recipient(db, batch_one, "a@example.com")
        _make_recipient(db, batch_two, "b@example.com")

        page = BroadcastRecipientResultsService(db).get_page(batch_one, Params())

        assert [item.email for item in page.items] == ["a@example.com"]
