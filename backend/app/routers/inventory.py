from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from app.dependencies import require_admin
from app.models.shuttle import ShuttleBatch, ShuttleBatchCreate, ShuttleBatchUpdate
import app.services.shuttle_service as shuttle_service

router = APIRouter(prefix="/inventory")


@router.get("", response_model=list[ShuttleBatch])
async def list_inventory(_=Depends(require_admin)):
    return shuttle_service.get_all()


@router.post("", response_model=ShuttleBatch, status_code=201)
async def create_batch(data: ShuttleBatchCreate, _=Depends(require_admin)):
    return shuttle_service.create(data)


@router.patch("/{batch_id}", response_model=ShuttleBatch)
async def update_batch(batch_id: UUID, data: ShuttleBatchUpdate, _=Depends(require_admin)):
    try:
        return shuttle_service.update(batch_id, data)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 422
        raise HTTPException(status_code=status_code, detail=detail)
