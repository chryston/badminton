from uuid import UUID

from fastapi import APIRouter, Depends

from app.dependencies import require_admin
from app.models.court_slot import CourtSlot, CourtSlotCreate
import app.services.court_slot_service as court_slot_service

router = APIRouter()


@router.get("/sessions/{session_id}/court-slots", response_model=list[CourtSlot])
def list_court_slots(session_id: UUID, _=Depends(require_admin)):
    return court_slot_service.get_by_session(session_id)


@router.post("/sessions/{session_id}/court-slots", response_model=CourtSlot, status_code=201)
def add_court_slot(session_id: UUID, data: CourtSlotCreate, _=Depends(require_admin)):
    return court_slot_service.add_slot(session_id, data)


@router.delete("/sessions/{session_id}/court-slots/{slot_id}", status_code=204)
def remove_court_slot(session_id: UUID, slot_id: UUID, _=Depends(require_admin)):
    court_slot_service.remove_slot(slot_id)
