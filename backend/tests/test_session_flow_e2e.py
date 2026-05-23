"""
E2E test: Complete session lifecycle

Simulates the real user workflow via the FastAPI TestClient:
  1. Admin creates a session
  2. Session is published (bot announcement mocked)
  3. A guest player is added to the roster
  4. Admin verifies payment
  5. Admin completes the session (no shuttle usage)
  6. P&L is calculated and returned

Mocking strategy:
  - app.db.client._service_client: replaced with a sequential mock whose
    execute() side_effect consumes pre-built responses in call order.
  - bot_runner.build / start_polling: no-ops to avoid Telegram API calls.
  - require_admin dependency: overridden to bypass JWT + DB admin check.
"""
from unittest.mock import MagicMock, AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

_SESSION_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
_VENUE_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
_ENTRY_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
_TS = "2025-01-01T10:00:00+00:00"

_SESSION_INTERNAL = {
    "id": _SESSION_ID,
    "venue_id": _VENUE_ID,
    "date": "2025-06-15",
    "start_time": "09:00:00",
    "end_time": "11:00:00",
    "courts_booked": "1",
    "num_courts": 1,
    "skill_level": "HB - LI",
    "pub_fee": 10.0,
    "max_pax": 12,
    "status": "internal",
    "telegram_message_id": None,
    "paynow_player_id": None,
    "created_at": _TS,
}

_SESSION_PUBLISHED = {**_SESSION_INTERNAL, "status": "published"}
_SESSION_COMPLETED = {**_SESSION_INTERNAL, "status": "completed"}

_ENTRY_UNPAID = {
    "id": _ENTRY_ID,
    "session_id": _SESSION_ID,
    "player_id": None,
    "guest_name": "Alice",
    "player_type": "guest",
    "payment_status": "unpaid",
    "is_waitlisted": False,
    "position": 1,
    "joined_at": _TS,
    "created_at": _TS,
}
_ENTRY_PAID = {**_ENTRY_UNPAID, "payment_status": "verified_paid"}

_VENUE_ROW = {
    "id": _VENUE_ID,
    "name": "Test Hall",
    "court_cost_per_hour": 15.0,
    "default_pub_fee": 10.0,
    "created_at": _TS,
}

def _session_with_roster():
    """
    Returns a fresh dict for each call.

    IMPORTANT: get_by_id() calls row.pop("roster_entries") and row.pop("shuttle_usage")
    which mutates the dict in place. If the same dict were reused across two execute()
    side_effect calls, the second call would receive a dict missing those keys and raise
    a KeyError inside the service. Always generate a new dict here.
    """
    return {
        **_SESSION_COMPLETED,
        "roster_entries": [dict(_ENTRY_PAID)],
        "shuttle_usage": [],
    }


def _make_mock_db():
    """Build a chaining mock Supabase client. All query builder methods return self."""
    client = MagicMock()
    builder = MagicMock()
    for method in ("select", "insert", "update", "delete", "eq", "order", "limit", "maybe_single", "in_"):
        getattr(builder, method).return_value = builder
    client.table.return_value = builder
    return client, builder


def test_complete_session_lifecycle():
    """Full E2E: create → publish → join (guest) → verify payment → complete → P&L."""
    from app.main import app
    from app.dependencies import require_admin

    mock_client, mock_builder = _make_mock_db()

    # Responses consumed in the exact order execute() is called across all service calls.
    mock_builder.execute.side_effect = [
        # --- create session ---
        MagicMock(data=[_SESSION_INTERNAL]),        # sessions.insert → new session
        MagicMock(data=[]),                          # players(is_internal=True) → none
        # --- publish session ---
        MagicMock(data=[{"status": "internal"}]),   # sessions.select("status")
        MagicMock(data=[_SESSION_PUBLISHED]),        # sessions.update(published)
        # --- add guest ---
        MagicMock(data=[{"max_pax": 12}]),           # sessions.select("max_pax")
        MagicMock(data=[]),                          # roster_entries active count → 0
        MagicMock(data=[]),                          # roster_entries max position → none
        MagicMock(data=[_ENTRY_UNPAID]),             # roster_entries.insert
        # --- verify payment ---
        MagicMock(data=[_ENTRY_PAID]),               # roster_entries.update(verified_paid)
        # --- complete session (no shuttle usages) ---
        MagicMock(data=[{"status": "published"}]),  # sessions.select("status")
        MagicMock(data=[_SESSION_COMPLETED]),        # sessions.update(completed)
        MagicMock(data=[_session_with_roster()]),     # get_by_id (nested select)
        # --- get P&L ---
        MagicMock(data=[_session_with_roster()]),     # get_by_id
        MagicMock(data=[_VENUE_ROW]),                # venues.select (court_cost_per_hour)
        MagicMock(data=[]),                          # players(is_internal=True) for exclusion
    ]

    app.dependency_overrides[require_admin] = lambda: None

    try:
        with (
            patch("app.db.client._service_client", mock_client),
            patch("app.bot.runner.bot_runner.build"),
            patch("app.bot.runner.bot_runner.start_polling", new_callable=AsyncMock),
        ):
            with TestClient(app) as client:
                headers = {"Authorization": "Bearer test-token"}

                # 1. Create session
                resp = client.post(
                    "/api/v1/sessions",
                    json={
                        "venue_id": _VENUE_ID,
                        "date": "2025-06-15",
                        "start_time": "09:00:00",
                        "end_time": "11:00:00",
                        "courts_booked": "1",
                        "num_courts": 1,
                        "skill_level": "HB - LI",
                        "pub_fee": 10.0,
                        "max_pax": 12,
                    },
                    headers=headers,
                )
                assert resp.status_code == 201, resp.text
                assert resp.json()["status"] == "internal"

                # 2. Publish session
                resp = client.post(f"/api/v1/sessions/{_SESSION_ID}/publish", headers=headers)
                assert resp.status_code == 200, resp.text
                assert resp.json()["status"] == "published"

                # 3. Add a guest player to the roster
                resp = client.post(
                    f"/api/v1/sessions/{_SESSION_ID}/roster/guest",
                    json={"guest_name": "Alice"},
                    headers=headers,
                )
                assert resp.status_code == 201, resp.text
                entry = resp.json()
                assert entry["guest_name"] == "Alice"
                assert entry["payment_status"] == "unpaid"
                assert entry["is_waitlisted"] is False

                # 4. Verify Alice's payment
                resp = client.post(
                    f"/api/v1/sessions/{_SESSION_ID}/roster/{_ENTRY_ID}/verify",
                    headers=headers,
                )
                assert resp.status_code == 200, resp.text
                assert resp.json()["payment_status"] == "verified_paid"

                # 5. Complete session with no shuttle usage
                resp = client.post(
                    f"/api/v1/sessions/{_SESSION_ID}/complete",
                    json=[],
                    headers=headers,
                )
                assert resp.status_code == 200, resp.text
                completed = resp.json()
                assert completed["status"] == "completed"
                assert len(completed["roster"]) == 1
                assert completed["roster"][0]["payment_status"] == "verified_paid"

                # 6. Fetch P&L
                resp = client.get(f"/api/v1/sessions/{_SESSION_ID}/pnl", headers=headers)
                assert resp.status_code == 200, resp.text
                pnl = resp.json()

                # 1 external verified_paid player × $10 = $10 income
                # 2h × 1 court × $15/hr = $30 court cost
                # 0 shuttles → net = $10 - $30 = -$20
                assert pnl["total_fees_collected"] == 10.0
                assert pnl["court_cost"] == 30.0
                assert pnl["shuttle_cost"] == 0.0
                assert pnl["net"] == -20.0
                assert pnl["external_paid_count"] == 1
    finally:
        app.dependency_overrides.clear()
