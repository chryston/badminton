import asyncio
from uuid import UUID
from fastapi import APIRouter, Depends, Body
from app.dependencies import require_admin
from app.models.session import Session, SessionCreate, SessionUpdate, SessionWithRoster, CancelRequest
from app.models.shuttle import ShuttleUsageCreate
import app.services.session_service as session_service
from app.bot.runner import bot_runner

router = APIRouter(prefix="/sessions")


@router.get("", response_model=list[Session])
async def list_sessions(_=Depends(require_admin)):
    return session_service.get_all()


@router.post("", response_model=Session, status_code=201)
async def create_session(data: SessionCreate, _=Depends(require_admin)):
    return session_service.create(data)


@router.get("/{session_id}", response_model=SessionWithRoster)
async def get_session(session_id: UUID, _=Depends(require_admin)):
    return session_service.get_by_id(session_id)


@router.patch("/{session_id}", response_model=Session)
async def update_session(session_id: UUID, data: SessionUpdate, _=Depends(require_admin)):
    return session_service.update(session_id, data)


@router.post("/{session_id}/publish", response_model=Session)
async def publish_session(session_id: UUID, _=Depends(require_admin)):
    session = session_service.publish(session_id)
    asyncio.create_task(bot_runner.post_session_announcement(session))
    return session


@router.post("/{session_id}/complete", response_model=SessionWithRoster)
async def complete_session(
    session_id: UUID,
    shuttle_usages: list[ShuttleUsageCreate] = Body(default=[]),
    _=Depends(require_admin),
):
    return session_service.complete(session_id, shuttle_usages)


@router.post("/{session_id}/cancel", response_model=Session)
async def cancel_session(
    session_id: UUID,
    body: CancelRequest,
    _=Depends(require_admin),
):
    session = session_service.cancel(session_id, body.reason)
    asyncio.create_task(bot_runner.post_cancellation_message(session, body.reason))
    return session
