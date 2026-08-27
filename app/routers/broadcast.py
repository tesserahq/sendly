import json
from json import JSONDecodeError
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi_pagination import Page, Params
from fastapi_pagination.ext.sqlalchemy import paginate
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
from app.models.broadcast_batch import BroadcastBatch
from app.repositories.broadcast_repository import BroadcastRepository
from app.schemas.broadcast import (
    BroadcastBatchSummary,
    BroadcastCreateRequest,
    BroadcastRecipientResult,
    BroadcastSendResponse,
    BroadcastStatusResponse,
)
from app.services.broadcast_recipient_results_service import (
    BroadcastRecipientResultsService,
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


@router.get("", response_model=Page[BroadcastBatchSummary])
def list_broadcasts(
    project_id: Annotated[
        Optional[UUID],
        Query(description="Project ID to filter broadcast batches by"),
    ] = None,
    db: Session = Depends(get_db),
    params: Params = Depends(),
    _authorized: bool = Depends(rbac["read"]),
) -> Page[BroadcastBatchSummary]:
    """List broadcast batches, newest first, including each batch's
    prepared_count/finished progress (denormalized columns, updated at the
    prepare/send write points — see BroadcastRepository.increment_prepared_count
    and .maybe_mark_finished)."""
    repo = BroadcastRepository(db)
    query = repo.get_batches_query(project_id=project_id)
    return paginate(query, params)


async def _authorize_batch_read(batch: BroadcastBatch, request: Request) -> None:
    """Shared authorization for both batch-scoped GET endpoints.

    batch_id is server-generated and globally unique, so the DB lookup that
    finds `batch` isn't scoped by project_id — but that means project_id
    can't be trusted from the caller for authorization either. Callers must
    load the batch first, then authorize against its *actual* project_id.
    Omitting project_id (or passing an unrelated one) no longer bypasses
    tenant isolation: a caller is only authorized if they're allowed to
    read `sendly.broadcast` in the batch's real project (or hold a
    global/super-admin grant, via Custos's own domain semantics).
    """
    check_read = authorize(
        resource=f"{PREFIX}.{RESOURCE}",
        action=RBACActions.READ,
        domain_resolver=fixed_domain_resolver(
            str(batch.project_id) if batch.project_id is not None else "*"
        ),
    )
    await check_read(request)


@router.get("/{batch_id}", response_model=BroadcastStatusResponse)
async def get_broadcast(
    batch_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> BroadcastStatusResponse:
    """Accept-time counts plus prepare/send progress for one batch, read
    from the denormalized prepared_count/finished columns."""
    repo = BroadcastRepository(db)
    batch = repo.get_batch_by_batch_id(batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Broadcast batch not found")

    await _authorize_batch_read(batch, request)

    return BroadcastStatusResponse(
        batch_id=batch.batch_id,
        queued_count=batch.queued_count,
        suppressed_count=batch.suppressed_count,
        prepared_count=batch.prepared_count,
        finished=batch.finished,
        delivered_count=batch.delivered_count,
        bounced_count=batch.bounced_count,
        complained_count=batch.complained_count,
        opened_count=batch.opened_count,
        clicked_count=batch.clicked_count,
    )


@router.get("/{batch_id}/recipients", response_model=Page[BroadcastRecipientResult])
async def list_broadcast_recipients(
    batch_id: str,
    request: Request,
    db: Session = Depends(get_db),
    params: Params = Depends(),
) -> Page[BroadcastRecipientResult]:
    """Paginated per-recipient results for one batch: submitted identity,
    preparation/suppression outcome, resulting email identity/status (when
    one exists), and first-open/first-click timestamps. Suppressed
    recipients and preparation failures remain visible with null
    email/engagement fields."""
    repo = BroadcastRepository(db)
    batch = repo.get_batch_by_batch_id(batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Broadcast batch not found")

    await _authorize_batch_read(batch, request)

    return BroadcastRecipientResultsService(db).get_page(batch, params)
