from datetime import date, datetime
from uuid import UUID
from pydantic import BaseModel


class ShuttleBatch(BaseModel):
    id: UUID
    batch_name: str
    brand: str
    owner_label: str | None = None
    cost_per_tube: float
    shuttles_per_tube: int
    cost_per_shuttle: float  # GENERATED column, read-only
    remaining_count: int
    is_active: bool = True
    purchased_at: date | None = None
    created_at: datetime


class ShuttleBatchCreate(BaseModel):
    batch_name: str
    brand: str
    owner_label: str | None = None
    cost_per_tube: float
    shuttles_per_tube: int
    remaining_count: int = 0
    is_active: bool = True
    purchased_at: date | None = None


class ShuttleBatchUpdate(BaseModel):
    batch_name: str | None = None
    brand: str | None = None
    owner_label: str | None = None
    cost_per_tube: float | None = None
    shuttles_per_tube: int | None = None
    remaining_count: int | None = None
    is_active: bool | None = None


class ShuttleUsage(BaseModel):
    id: UUID
    session_id: UUID
    batch_id: UUID
    count_used: int
    created_at: datetime


class ShuttleUsageCreate(BaseModel):
    batch_id: UUID
    count_used: int
