from uuid import UUID
from fastapi import APIRouter, Depends
from app.dependencies import require_admin
from app.models.roster import PnLResult
import app.services.pnl_service as pnl_service
from app.routers._utils import raise_for_value_error

router = APIRouter(prefix="/sessions")


@router.get("/{session_id}/pnl", response_model=PnLResult)
async def get_session_pnl(session_id: UUID, _=Depends(require_admin)):
    try:
        return pnl_service.get_session_pnl(session_id)
    except ValueError as e:
        raise_for_value_error(e)
