from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Body
from app.dependencies import require_admin
from app.models.session import Session, SessionCreate, SessionUpdate, SessionWithRoster
from app.models.shuttle import ShuttleUsageCreate
import app.services.session_service as session_service

router = APIRouter(prefix="/sessions")


def _not_found(err: ValueError) -> bool:
    return "not found" in str(err).lower()


@router.get("", response_model=list[Session])
async def list_sessions(_=Depends(require_admin)):
    return session_service.get_all()


@router.post("", response_model=Session, status_code=201)
async def create_session(data: SessionCreate, _=Depends(require_admin)):
    return session_service.create(data)


@router.get("/{session_id}", response_model=SessionWithRoster)
async def get_session(session_id: UUID, _=Depends(require_admin)):
    try:
        return session_service.get_by_id(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.patch("/{session_id}", response_model=Session)
async def update_session(session_id: UUID, data: SessionUpdate, _=Depends(require_admin)):
    try:
        return session_service.update(session_id, data)
    except ValueError as exc:
        status_code = 404 if _not_found(exc) else 422
        raise HTTPException(status_code=status_code, detail=str(exc))


@router.post("/{session_id}/publish", response_model=Session)
async def publish_session(session_id: UUID, _=Depends(require_admin)):
    try:
        session = session_service.publish(session_id)
    except ValueError as exc:
        status_code = 404 if _not_found(exc) else 422
        raise HTTPException(status_code=status_code, detail=str(exc))

    # TODO(T6): trigger bot to post session announcement
    # await bot_runner.post_session_announcement(session)
    pass

    return session


@router.post("/{session_id}/complete", response_model=SessionWithRoster)
async def complete_session(
    session_id: UUID,
    shuttle_usages: list[ShuttleUsageCreate] = Body(default=[]),
    _=Depends(require_admin),
):
    try:
        return session_service.complete(session_id, shuttle_usages)
    except ValueError as exc:
        status_code = 404 if _not_found(exc) else 422
        raise HTTPException(status_code=status_code, detail=str(exc))
