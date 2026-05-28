from unittest.mock import MagicMock, call, patch
from uuid import uuid4
from datetime import datetime, timezone

import pytest

from app.models.roster import RosterEntry

_NOW = datetime.now(timezone.utc).isoformat()
_SESSION_ID = uuid4()
_PLAYER_ID = uuid4()
_ENTRY_ID = uuid4()
_TELEGRAM_ID = 99999


def _roster_row(player_id=_PLAYER_ID, is_waitlisted=False, payment_status="unpaid"):
    return {
        "id": str(_ENTRY_ID),
        "session_id": str(_SESSION_ID),
        "player_id": str(player_id),
        "guest_name": None,
        "player_type": "registered",
        "payment_status": payment_status,
        "is_waitlisted": is_waitlisted,
        "position": 1,
        "joined_at": _NOW,
        "created_at": _NOW,
    }


def _player_row():
    return {
        "id": str(_PLAYER_ID),
        "name": "Alice",
        "telegram_id": _TELEGRAM_ID,
        "is_internal": False,
        "is_admin": False,
        "phone": None,
        "skill_level": "HB",
        "notes": None,
        "created_at": _NOW,
    }


def test_remove_player_deletes_roster_entry():
    """remove_player finds the player's entry and deletes it via remove_entry."""
    import app.services.roster_service as roster_service

    with (
        patch("app.services.roster_service.player_service.get_by_telegram_id") as mock_player,
        patch("app.services.roster_service.get_service_client") as mock_client_fn,
        patch("app.services.roster_service.remove_entry") as mock_remove,
    ):
        from app.models.player import Player
        mock_player.return_value = Player(**_player_row())
        client = MagicMock()
        client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
            {"id": str(_ENTRY_ID)}
        ]
        mock_client_fn.return_value = client
        removed_entry = RosterEntry(**_roster_row())
        mock_remove.return_value = removed_entry

        result = roster_service.remove_player(_SESSION_ID, _TELEGRAM_ID)

    assert result.id == removed_entry.id
    assert result.session_id == removed_entry.session_id


def test_remove_player_raises_if_not_on_roster():
    """remove_player raises ValueError when player has no roster entry for the session."""
    import app.services.roster_service as roster_service

    with (
        patch("app.services.roster_service.player_service.get_by_telegram_id") as mock_player,
        patch("app.services.roster_service.get_service_client") as mock_client_fn,
    ):
        from app.models.player import Player
        mock_player.return_value = Player(**_player_row())
        client = MagicMock()
        client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
        mock_client_fn.return_value = client

        with pytest.raises(ValueError, match="not on this session"):
            roster_service.remove_player(_SESSION_ID, _TELEGRAM_ID)


def test_remove_player_raises_if_player_unknown():
    """remove_player raises ValueError when telegram_id not found."""
    import app.services.roster_service as roster_service

    with patch("app.services.roster_service.player_service.get_by_telegram_id", return_value=None):
        with pytest.raises(ValueError, match="Player not found"):
            roster_service.remove_player(_SESSION_ID, _TELEGRAM_ID)
