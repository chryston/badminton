from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class FundEntry(BaseModel):
    id: UUID
    description: str
    amount: float  # positive = deposit/income; negative = expense
    created_at: datetime


class FundEntryCreate(BaseModel):
    description: str = Field(min_length=1)
    amount: float

    @field_validator("amount")
    @classmethod
    def amount_not_zero(cls, v: float) -> float:
        if v == 0:
            raise ValueError("amount must not be zero")
        return v


class FundBalance(BaseModel):
    entries: list[FundEntry]
    entries_total: float
