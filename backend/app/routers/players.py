from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from app.dependencies import require_admin
from app.models.player import Player, PlayerCreate, PlayerUpdate
import app.services.player_service as player_service

router = APIRouter(prefix="/players")


@router.get("", response_model=list[Player])
async def list_players(_=Depends(require_admin)):
    return player_service.get_all()


@router.post("", response_model=Player, status_code=201)
async def create_player(data: PlayerCreate, _=Depends(require_admin)):
    return player_service.create(data)


@router.patch("/{player_id}", response_model=Player)
async def update_player(player_id: UUID, data: PlayerUpdate, _=Depends(require_admin)):
    try:
        return player_service.update(player_id, data)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 422
        raise HTTPException(status_code=status_code, detail=detail)
