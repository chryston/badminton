from unittest.mock import MagicMock, patch
from uuid import uuid4
from datetime import datetime, timezone
import app.services.session_service as session_service


def _make_session_row(status: str = "published") -> dict:
    sid = str(uuid4())
    return {
        "id": sid,
        "venue_id": str(uuid4()),
        "date": "2026-06-01",
        "start_time": "20:00:00",
        "end_time": "22:00:00",
        "duration_hours": 2.0,
        "courts_booked": "3 & 4",
        "num_courts": 2,
        "min_skill_level": "HB",
        "max_skill_level": "LI",
        "pub_fee": 12.0,
        "max_pax": 12,
        "status": status,
        "telegram_message_id": None,
        "paynow_player_id": None,
        "cancellation_reason": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _make_db_client(session_row: dict):
    client = MagicMock()
    builder = MagicMock()
    builder.execute.return_value.data = [session_row]
    client.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        session_row
    ]
    client.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [
        {**session_row, "status": "cancelled"}
    ]
    return client


def test_cancel_published_session():
    """Cancelling a published session sets status to cancelled."""
    reason = "Not enough players"
    row = _make_session_row("published")
    client = _make_db_client(row)
    with patch("app.services.session_service.get_service_client", return_value=client):
        result = session_service.cancel(uuid4(), reason)
    update_payload = client.table.return_value.update.call_args[0][0]
    assert update_payload["cancellation_reason"] == reason
    assert result.status == "cancelled"


def test_cannot_cancel_completed_session():
    """Completed sessions cannot be cancelled."""
    row = _make_session_row("completed")
    client = _make_db_client(row)
    with patch("app.services.session_service.get_service_client", return_value=client):
        try:
            session_service.cancel(uuid4(), "reason")
            assert False, "Expected ValueError"
        except ValueError as e:
            assert "completed" in str(e).lower()
