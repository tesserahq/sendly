import json
from json import JSONDecodeError
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.auth.rbac import build_rbac_dependencies
from app.commands.send_broadcast_command import SendBroadcastCommand
from app.db import get_db
from app.repositories.broadcast_repository import BroadcastRepository
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
def get_broadcast(
    batch_id: str,
    project_id: UUID = Query(..., description="Project ID that owns this batch"),
    db: Session = Depends(get_db),
    _authorized: bool = Depends(rbac["read"]),
) -> BroadcastStatusResponse:
    """Accept-time counts plus live prepare-stage progress for one batch."""
    repo = BroadcastRepository(db)
    batch = repo.get_batch_by_batch_id(project_id, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Broadcast batch not found")

    prepared_count = repo.count_prepared(batch.id)
    return BroadcastStatusResponse(
        batch_id=batch.batch_id,
        queued_count=batch.queued_count,
        suppressed_count=batch.suppressed_count,
        prepared_count=prepared_count,
    )
