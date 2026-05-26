"""Unit tests for court_slot_service — behaviour, minimal mocking."""
from datetime import time, datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.models.court_slot import CourtSlotCreate
from app.services.court_slot_service import get_by_session, add_slot, remove_slot

_SESSION_ID = uuid4()
_SLOT_ID = uuid4()
_BOOKER_ID = uuid4()
_NOW = datetime.now(timezone.utc)

_SLOT_ROW = {
    "id": str(_SLOT_ID),
    "session_id": str(_SESSION_ID),
    "court_label": "Court 1",
    "from_time": "09:00:00",
    "to_time": "11:00:00",
    "booker_player_id": str(_BOOKER_ID),
    "created_at": _NOW.isoformat(),
}


def _make_mock_db():
    client = MagicMock()
    builder = MagicMock()
    for method in ("select", "insert", "update", "delete", "eq", "order", "in_"):
        getattr(builder, method).return_value = builder
    client.table.return_value = builder
    return client, builder


def test_get_by_session_returns_slots():
    """Returns CourtSlot objects for the given session."""
    client, builder = _make_mock_db()
    builder.execute.return_value = MagicMock(data=[_SLOT_ROW])

    with patch("app.db.client._service_client", client):
        slots = get_by_session(_SESSION_ID)

    assert len(slots) == 1
    assert slots[0].court_label == "Court 1"
    assert slots[0].from_time == time(9, 0)
    assert slots[0].booker_player_id == _BOOKER_ID


def test_get_by_session_empty():
    """Returns empty list when session has no slots."""
    client, builder = _make_mock_db()
    builder.execute.return_value = MagicMock(data=[])

    with patch("app.db.client._service_client", client):
        slots = get_by_session(_SESSION_ID)

    assert slots == []


def test_add_slot_inserts_and_returns():
    """Inserts a court slot and returns the persisted CourtSlot."""
    client, builder = _make_mock_db()
    builder.execute.return_value = MagicMock(data=[_SLOT_ROW])

    data = CourtSlotCreate(
        court_label="Court 1",
        from_time=time(9, 0),
        to_time=time(11, 0),
        booker_player_id=_BOOKER_ID,
    )

    with patch("app.db.client._service_client", client):
        slot = add_slot(_SESSION_ID, data)

    assert slot.court_label == "Court 1"
    assert slot.booker_player_id == _BOOKER_ID


def test_remove_slot_calls_delete():
    """Calls delete with the correct slot id."""
    client, builder = _make_mock_db()
    builder.execute.return_value = MagicMock(data=[])

    with patch("app.db.client._service_client", client):
        remove_slot(_SLOT_ID)

    builder.delete.assert_called_once()
    builder.eq.assert_called_with("id", str(_SLOT_ID))
