from unittest.mock import MagicMock, patch
from uuid import uuid4
from app.services import roster_service
from app.models.player import Player
from app.models.roster import RosterEntry
from datetime import datetime, timezone


def _make_player(is_internal: bool) -> Player:
    return Player(
        id=uuid4(),
        name="Test Player",
        skill_level="LI",
        phone=None,
        is_internal=is_internal,
        telegram_id=123456,
        notes=None,
        created_at=datetime.now(timezone.utc),
    )


def _make_db_client():
    """Build a mock DB client that handles all DB operations in add_player.

    - sessions table: returns max_pax=10 for the session lookup
    - roster_entries selects: return empty data (player not yet on roster, no prior positions)
    - roster_entries insert: echoes back the inserted row so assertions on the
      returned RosterEntry reflect what the code actually set
    """
    now = datetime.now(timezone.utc).isoformat()

    def _insert_and_return(row):
        mock = MagicMock()
        mock.execute.return_value.data = [
            {"id": str(uuid4()), "guest_name": None, "is_waitlisted": False,
             "joined_at": now, "created_at": now, **row}
        ]
        return mock

    def _table_side_effect(table_name):
        table_mock = MagicMock()
        if table_name == "sessions":
            # Session lookup: return a row with max_pax
            table_mock.select.return_value.eq.return_value.execute.return_value.data = [
                {"max_pax": 10}
            ]
        else:
            # roster_entries: selects return empty lists; inserts echo the row
            empty = MagicMock()
            empty.execute.return_value.data = []
            table_mock.select.return_value.eq.return_value.eq.return_value = empty
            table_mock.select.return_value.eq.return_value.order.return_value.limit.return_value = empty
            table_mock.insert.side_effect = _insert_and_return
        return table_mock

    client = MagicMock()
    client.table.side_effect = _table_side_effect
    return client


def test_external_player_added_as_unpaid():
    """External players join with payment_status='unpaid'."""
    player = _make_player(is_internal=False)
    client = _make_db_client()
    with (
        patch("app.services.roster_service.get_service_client", return_value=client),
        patch("app.services.player_service.get_by_telegram_id", return_value=None),
        patch("app.services.player_service.create", return_value=player),
        patch("app.services.roster_service.get_active_count", return_value=0),
    ):
        entry, _ = roster_service.add_player(uuid4(), 123456, "External Player")
    assert entry.payment_status == "unpaid"


def test_internal_player_auto_marked_verified_paid():
    """Internal players are automatically marked verified_paid when they join."""
    player = _make_player(is_internal=True)
    client = _make_db_client()
    with (
        patch("app.services.roster_service.get_service_client", return_value=client),
        patch("app.services.player_service.get_by_telegram_id", return_value=None),
        patch("app.services.player_service.create", return_value=player),
        patch("app.services.roster_service.get_active_count", return_value=0),
    ):
        entry, _ = roster_service.add_player(uuid4(), 123456, "Internal Player")
    assert entry.payment_status == "verified_paid"
