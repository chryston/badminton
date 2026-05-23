from datetime import datetime
from uuid import UUID
from pydantic import BaseModel


class RosterEntry(BaseModel):
    id: UUID
    session_id: UUID
    player_id: UUID | None = None
    guest_name: str | None = None
    player_type: str  # registered | guest
    payment_status: str  # unpaid | verified_paid
    is_waitlisted: bool = False
    position: int
    joined_at: datetime
    created_at: datetime

    @property
    def display_name(self) -> str:
        return self.guest_name or ""  # name resolved by service layer


class RosterEntryCreate(BaseModel):
    guest_name: str  # for manually adding external players


class PnLResult(BaseModel):
    session_id: UUID
    total_fees_collected: float
    court_cost: float
    shuttle_cost: float
    net: float
    verified_paid_count: int
    total_roster_count: int
