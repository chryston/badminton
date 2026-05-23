from datetime import date, datetime, time
from uuid import UUID
from pydantic import BaseModel
from app.models.shuttle import ShuttleUsage


class Session(BaseModel):
    id: UUID
    venue_id: UUID
    date: date
    start_time: time
    end_time: time
    courts_booked: str
    num_courts: int
    skill_level: str
    pub_fee: float
    max_pax: int
    status: str  # internal | published | completed
    telegram_message_id: int | None = None
    paynow_player_id: UUID | None = None
    created_at: datetime


class SessionCreate(BaseModel):
    venue_id: UUID
    date: date
    start_time: time
    end_time: time
    courts_booked: str
    num_courts: int = 1
    skill_level: str = "HB - LI"
    pub_fee: float
    max_pax: int
    paynow_player_id: UUID | None = None


class SessionUpdate(BaseModel):
    courts_booked: str | None = None
    skill_level: str | None = None
    pub_fee: float | None = None
    max_pax: int | None = None
    paynow_player_id: UUID | None = None


class SessionWithRoster(Session):
    roster: list["RosterEntry"] = []
    shuttle_usage: list[ShuttleUsage] = []
    active_count: int = 0
    waitlist_count: int = 0


# Forward reference resolved below
from app.models.roster import RosterEntry
SessionWithRoster.model_rebuild()
