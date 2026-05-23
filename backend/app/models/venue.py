from datetime import datetime
from uuid import UUID
from pydantic import BaseModel


class Venue(BaseModel):
    id: UUID
    name: str
    court_cost_per_hour: float
    default_pub_fee: float
    created_at: datetime
