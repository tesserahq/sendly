"""Deep module for GET /broadcasts/{batch_id}/recipients.

Owns the left join from broadcast recipients to their resulting email, a
stable pagination order, and result projection, so the router (which already
resolves and authorizes the batch, same as GET /broadcasts/{batch_id}) never
has to assemble the join itself. Reads only denormalized fields on Email
(status, opened_at, clicked_at) — never joins email_events — so one page's
cost stays proportional to the requested page size, not to accumulated
webhook history.
"""

from __future__ import annotations

from typing import List, Tuple

from fastapi_pagination import Page, Params
from fastapi_pagination.ext.sqlalchemy import paginate
from sqlalchemy.orm import Session

from app.models.broadcast_batch import BroadcastBatch
from app.models.broadcast_recipient import BroadcastRecipient
from app.models.email import Email
from app.schemas.broadcast import BroadcastRecipientResult

_Row = Tuple[BroadcastRecipient, "Email | None"]


class BroadcastRecipientResultsService:
    def __init__(self, db: Session):
        self.db = db

    def get_page(
        self, batch: BroadcastBatch, params: Params
    ) -> Page[BroadcastRecipientResult]:
        """Paginated recipient results for one already-authorized batch.

        Ordered by (created_at, id) — a unique tie-breaker so pages remain
        stable across additions to the batch, letting a caller traverse
        every page without skipping or duplicating recipients.
        """
        query = (
            self.db.query(BroadcastRecipient, Email)
            .outerjoin(Email, BroadcastRecipient.email_id == Email.id)
            .filter(BroadcastRecipient.broadcast_batch_id == batch.id)
            .order_by(BroadcastRecipient.created_at.asc(), BroadcastRecipient.id.asc())
        )
        return paginate(query, params, transformer=self._to_results)

    @staticmethod
    def _to_results(rows: List[_Row]) -> List[BroadcastRecipientResult]:
        return [
            BroadcastRecipientResult(
                id=recipient.id,
                client_reference_id=recipient.client_reference_id,
                email=recipient.email,
                suppressed=recipient.suppressed,
                prepared=recipient.prepared,
                email_id=email.id if email is not None else None,
                email_status=email.status if email is not None else None,
                opened_at=email.opened_at if email is not None else None,
                clicked_at=email.clicked_at if email is not None else None,
            )
            for recipient, email in rows
        ]
