from datetime import datetime
from uuid import UUID
from pydantic import BaseModel


class Player(BaseModel):
    id: UUID
    auth_user_id: UUID | None = None
    telegram_id: int | None = None
    name: str
    phone: str | None = None
    skill_level: str | None = None
    is_internal: bool = False
    is_admin: bool = False
    notes: str | None = None
    created_at: datetime


class PlayerCreate(BaseModel):
    name: str
    phone: str | None = None
    skill_level: str | None = None
    is_internal: bool = False
    is_admin: bool = False
    notes: str | None = None


class PlayerUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    skill_level: str | None = None
    is_internal: bool | None = None
    is_admin: bool | None = None
    notes: str | None = None
