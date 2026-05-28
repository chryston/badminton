from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class FundEntry(BaseModel):
    id: UUID
    description: str
    amount: float  # positive = deposit/income; negative = expense
    created_at: datetime


class FundEntryCreate(BaseModel):
    description: str
    amount: float


class FundBalance(BaseModel):
    entries: list[FundEntry]
    entries_total: float
