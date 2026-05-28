from unittest.mock import MagicMock, patch
from uuid import uuid4
from datetime import datetime, timezone

import pytest

_NOW = datetime.now(timezone.utc).isoformat()
_ENTRY_ROW = {"id": str(uuid4()), "description": "Opening balance", "amount": 150.0, "created_at": _NOW}


def _make_client(rows=None):
    rows = rows if rows is not None else []
    client = MagicMock()
    client.table.return_value.select.return_value.order.return_value.execute.return_value.data = rows
    client.table.return_value.insert.return_value.execute.return_value.data = rows[:1] if rows else [_ENTRY_ROW]
    return client


def test_get_entries_returns_fund_entries():
    with patch("app.services.fund_service.get_service_client", return_value=_make_client([_ENTRY_ROW])):
        import app.services.fund_service as fund_service
        entries = fund_service.get_entries()
    assert len(entries) == 1
    assert entries[0].amount == 150.0


def test_add_entry_inserts_row():
    inserted = {"id": str(uuid4()), "description": "Opening balance", "amount": 200.0, "created_at": _NOW}
    client = _make_client([inserted])
    client.table.return_value.insert.return_value.execute.return_value.data = [inserted]
    with patch("app.services.fund_service.get_service_client", return_value=client):
        import app.services.fund_service as fund_service
        from app.models.fund import FundEntryCreate
        entry = fund_service.add_entry(FundEntryCreate(description="Opening balance", amount=200.0))
    assert entry.amount == 200.0
    assert entry.description == "Opening balance"


def test_get_balance_sums_entries():
    rows = [
        {"id": str(uuid4()), "description": "Opening", "amount": 150.0, "created_at": _NOW},
        {"id": str(uuid4()), "description": "Shuttles", "amount": -40.0, "created_at": _NOW},
    ]
    with patch("app.services.fund_service.get_service_client", return_value=_make_client(rows)):
        import app.services.fund_service as fund_service
        balance = fund_service.get_balance()
    assert balance.entries_total == pytest.approx(110.0)
    assert len(balance.entries) == 2
