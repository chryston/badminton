import asyncio
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Response
from app.dependencies import require_admin
from app.models.roster import RosterEntry, RosterEntryCreate
import app.services.roster_service as roster_service
from app.bot.runner import bot_runner

router = APIRouter(prefix="/sessions")


@router.get("/{session_id}/roster", response_model=list[RosterEntry])
async def get_roster(session_id: UUID, _=Depends(require_admin)):
    return roster_service.get_session_roster(session_id)


@router.post("/{session_id}/roster/guest", response_model=RosterEntry, status_code=201)
async def add_guest(session_id: UUID, body: RosterEntryCreate, _=Depends(require_admin)):
    entry = roster_service.add_guest(session_id, body.guest_name)
    asyncio.create_task(bot_runner.edit_session_message(session_id))
    return entry


@router.delete("/{session_id}/roster/{entry_id}", status_code=204)
async def remove_roster_entry(
    session_id: UUID,
    entry_id: UUID,
    _=Depends(require_admin),
):
    removed = roster_service.remove_entry(entry_id)
    if removed is None:
        raise HTTPException(status_code=404, detail=f"RosterEntry {entry_id} not found")
    asyncio.create_task(bot_runner.edit_session_message(session_id))
    return Response(status_code=204)


@router.post("/{session_id}/roster/{entry_id}/verify", response_model=RosterEntry)
async def verify_payment(
    session_id: UUID,
    entry_id: UUID,
    _=Depends(require_admin),
):
    entry = roster_service.verify_payment(entry_id)
    asyncio.create_task(bot_runner.update_payment_in_message(session_id))
    return entry
