from datetime import datetime, time
from uuid import UUID
from pydantic import BaseModel


class CourtSlot(BaseModel):
    id: UUID
    session_id: UUID
    court_label: str
    from_time: time
    to_time: time
    booker_player_id: UUID
    created_at: datetime


class CourtSlotCreate(BaseModel):
    court_label: str
    from_time: time
    to_time: time
    booker_player_id: UUID
