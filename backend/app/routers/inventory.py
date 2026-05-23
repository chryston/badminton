from uuid import UUID
from fastapi import APIRouter, Depends
from app.dependencies import require_admin
from app.models.shuttle import ShuttleBatch, ShuttleBatchCreate, ShuttleBatchUpdate
import app.services.shuttle_service as shuttle_service
from app.routers._utils import raise_for_value_error

router = APIRouter(prefix="/inventory")


@router.get("", response_model=list[ShuttleBatch])
async def list_inventory(_=Depends(require_admin)):
    return shuttle_service.get_all()


@router.post("", response_model=ShuttleBatch, status_code=201)
async def create_batch(data: ShuttleBatchCreate, _=Depends(require_admin)):
    try:
        return shuttle_service.create(data)
    except ValueError as e:
        raise_for_value_error(e)


@router.patch("/{batch_id}", response_model=ShuttleBatch)
async def update_batch(batch_id: UUID, data: ShuttleBatchUpdate, _=Depends(require_admin)):
    try:
        return shuttle_service.update(batch_id, data)
    except ValueError as e:
        raise_for_value_error(e)
