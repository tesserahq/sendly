import json
from json import JSONDecodeError
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from tessera_sdk.server.dependencies.authorization import authorize

from app.auth.rbac import (
    PREFIX,
    RBACActions,
    build_rbac_dependencies,
    fixed_domain_resolver,
)
from app.commands.send_broadcast_command import SendBroadcastCommand
from app.db import get_db
from app.repositories.broadcast_repository import BroadcastRepository
from app.repositories.email_send_outbox_repository import EmailSendOutboxRepository
from app.schemas.broadcast import (
    BroadcastCreateRequest,
    BroadcastSendResponse,
    BroadcastStatusResponse,
)

router = APIRouter(
    prefix="/broadcasts",
    tags=["broadcasts"],
    responses={404: {"description": "Not found"}},
)


async def infer_project(request: Request) -> Optional[str]:
    project_id = request.query_params.get("project_id")

    if not project_id:
        body_bytes = await request.body()
        if body_bytes:
            try:
                body = json.loads(body_bytes)
                project_id = body.get("project_id")
            except JSONDecodeError:
                pass

    return project_id or "*"


RESOURCE = "broadcast"
rbac = build_rbac_dependencies(
    resource=RESOURCE,
    project_resolver=infer_project,
)


@router.post(
    "/send", response_model=BroadcastSendResponse, status_code=status.HTTP_200_OK
)
def send_broadcast(
    request: BroadcastCreateRequest,
    db: Session = Depends(get_db),
    _authorized: bool = Depends(rbac["create"]),
) -> BroadcastSendResponse:
    """Fan a single piece of content out to a list of recipients."""
    command = SendBroadcastCommand(db)
    batch = command.execute(request)

    return BroadcastSendResponse(
        batch_id=batch.batch_id,
        queued_count=batch.queued_count,
        suppressed_count=batch.suppressed_count,
    )


@router.get("/{batch_id}", response_model=BroadcastStatusResponse)
async def get_broadcast(
    batch_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> BroadcastStatusResponse:
    """Accept-time counts plus live prepare/send progress for one batch.

    batch_id is server-generated and globally unique, so the DB lookup
    below isn't scoped by project_id — but that means project_id can't be
    trusted from the caller for authorization either. Instead, this loads
    the batch first, then authorizes against its *actual* project_id.
    Omitting project_id (or passing an unrelated one) no longer bypasses
    tenant isolation: a caller is only authorized if they're allowed to
    read `sendly.broadcast` in the batch's real project (or hold a
    global/super-admin grant, via Custos's own domain semantics).
    """
    repo = BroadcastRepository(db)
    batch = repo.get_batch_by_batch_id(batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Broadcast batch not found")

    check_read = authorize(
        resource=f"{PREFIX}.{RESOURCE}",
        action=RBACActions.READ,
        domain_resolver=fixed_domain_resolver(
            str(batch.project_id) if batch.project_id is not None else "*"
        ),
    )
    await check_read(request)

    prepared_count = repo.count_prepared(batch.id)
    outbox_repo = EmailSendOutboxRepository(db)
    pending_send_count = outbox_repo.count_pending_for_batch(batch.batch_id)
    # Prepare must have created every expected Email row (or there'd be
    # nothing yet for the send stage to have picked up), and every outbox
    # entry it created must have been attempted.
    finished = prepared_count == batch.queued_count and pending_send_count == 0

    return BroadcastStatusResponse(
        batch_id=batch.batch_id,
        queued_count=batch.queued_count,
        suppressed_count=batch.suppressed_count,
        prepared_count=prepared_count,
        finished=finished,
    )
