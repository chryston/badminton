from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Response
from app.dependencies import require_admin
from app.models.roster import RosterEntry, RosterEntryCreate
import app.services.roster_service as roster_service
from app.routers._utils import raise_for_value_error

router = APIRouter(prefix="/sessions")


@router.get("/{session_id}/roster", response_model=list[RosterEntry])
async def get_roster(session_id: UUID, _=Depends(require_admin)):
    try:
        return roster_service.get_session_roster(session_id)
    except ValueError as e:
        raise_for_value_error(e)


@router.post("/{session_id}/roster/guest", response_model=RosterEntry, status_code=201)
async def add_guest(session_id: UUID, body: RosterEntryCreate, _=Depends(require_admin)):
    try:
        return roster_service.add_guest(session_id, body.guest_name)
    except ValueError as e:
        raise_for_value_error(e)


@router.delete("/{session_id}/roster/{entry_id}", status_code=204)
async def remove_roster_entry(
    session_id: UUID,  # noqa: ARG001 — required for RESTful path hierarchy
    entry_id: UUID,
    _=Depends(require_admin),
):
    removed = roster_service.remove_entry(entry_id)
    if removed is None:
        raise HTTPException(status_code=404, detail=f"RosterEntry {entry_id} not found")
    return Response(status_code=204)


@router.post("/{session_id}/roster/{entry_id}/verify", response_model=RosterEntry)
async def verify_payment(
    session_id: UUID,  # noqa: ARG001 — required for RESTful path hierarchy
    entry_id: UUID,
    _=Depends(require_admin),
):
    try:
        return roster_service.verify_payment(entry_id)
    except ValueError as e:
        raise_for_value_error(e)
