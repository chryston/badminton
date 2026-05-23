from fastapi import APIRouter, Depends
from app.dependencies import require_admin
from app.models.venue import Venue
import app.services.venue_service as venue_service

router = APIRouter(prefix="/venues")


@router.get("", response_model=list[Venue])
async def list_venues(_=Depends(require_admin)):
    return venue_service.get_all()
