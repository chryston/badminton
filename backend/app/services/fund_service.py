from app.db.client import get_service_client
from app.models.fund import FundBalance, FundEntry, FundEntryCreate


def get_entries() -> list[FundEntry]:
    client = get_service_client()
    result = client.table("fund_entries").select("*").order("created_at").execute()
    return [FundEntry(**row) for row in result.data]


def add_entry(data: FundEntryCreate) -> FundEntry:
    client = get_service_client()
    result = client.table("fund_entries").insert(data.model_dump(mode="json")).execute()
    return FundEntry(**result.data[0])


def get_balance() -> FundBalance:
    entries = get_entries()
    total = sum(e.amount for e in entries)
    return FundBalance(entries=entries, entries_total=round(total, 2))
