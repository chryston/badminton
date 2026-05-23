from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from app.dependencies import require_admin
from app.models.roster import PnLResult
import app.services.pnl_service as pnl_service

router = APIRouter(prefix="/sessions")


@router.get("/{session_id}/pnl", response_model=PnLResult)
async def get_session_pnl(session_id: UUID, _=Depends(require_admin)):
    try:
        return pnl_service.get_session_pnl(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
