import asyncio
from uuid import UUID
from fastapi import APIRouter, Depends, Body, HTTPException
from app.dependencies import require_admin
from app.models.session import Session, SessionCreate, SessionUpdate, SessionWithRoster, CancelRequest
from app.models.shuttle import ShuttleUsageCreate
import app.services.session_service as session_service
import app.services.venue_service as venue_service
import app.services.roster_service as roster_service
from app.bot.runner import bot_runner
from app.bot.message_formatter import format_recruit_message

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
    session_before = session_service.get_by_id(session_id)
    result = session_service.complete(session_id, shuttle_usages)
    asyncio.create_task(bot_runner.delete_session_message(session_before))
    return result


@router.post("/{session_id}/cancel", response_model=Session)
async def cancel_session(
    session_id: UUID,
    body: CancelRequest,
    _=Depends(require_admin),
):
    session = session_service.cancel(session_id, body.reason)
    asyncio.create_task(bot_runner.post_cancellation_message(session, body.reason))
    return session


@router.post("/{session_id}/recruit", response_model=dict)
async def recruit_players(session_id: UUID, _=Depends(require_admin)):
    """Generate a recruit message, send it to the admin group, and return the text."""
    session = session_service.get_by_id(session_id)
    if session.status != "published":
        raise HTTPException(status_code=400, detail="Session must be published to recruit players")
    venue = venue_service.get_by_id(session.venue_id)
    roster = roster_service.get_session_roster(session_id)
    active_count = sum(1 for e in roster if not e.is_waitlisted)
    slots_left = max(0, session.max_pax - active_count)
    message = format_recruit_message(session, slots_left, venue.name)
    asyncio.create_task(bot_runner.post_recruit_message(message))
    return {"message": message}
