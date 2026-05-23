from uuid import UUID
from fastapi import APIRouter, Depends
from app.dependencies import require_admin
from app.models.player import Player, PlayerCreate, PlayerUpdate
import app.services.player_service as player_service
from app.routers._utils import raise_for_value_error

router = APIRouter(prefix="/players")


@router.get("", response_model=list[Player])
async def list_players(_=Depends(require_admin)):
    return player_service.get_all()


@router.post("", response_model=Player, status_code=201)
async def create_player(data: PlayerCreate, _=Depends(require_admin)):
    try:
        return player_service.create(data)
    except ValueError as e:
        raise_for_value_error(e)


@router.patch("/{player_id}", response_model=Player)
async def update_player(player_id: UUID, data: PlayerUpdate, _=Depends(require_admin)):
    try:
        return player_service.update(player_id, data)
    except ValueError as e:
        raise_for_value_error(e)
