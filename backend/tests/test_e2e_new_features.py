# backend/tests/test_e2e_new_features.py
"""
E2E integration tests for the 5 new features.
Exercises HTTP endpoints via TestClient with mocked DB and bot.
Formatter/service-only behavior is tested in the unit test files.
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

_TS = "2026-01-01T10:00:00+00:00"
_SESSION_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
_VENUE_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
_ENTRY_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
_FUND_ID = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"

_SESSION_ROW = {
    "id": _SESSION_ID, "venue_id": _VENUE_ID,
    "date": "2026-05-31", "start_time": "20:00:00", "end_time": "22:00:00",
    "duration_hours": 2.0, "courts_booked": "Court 1 & 2", "num_courts": 2,
    "min_skill_level": "HB", "max_skill_level": "LI",
    "pub_fee": 12.0, "max_pax": 12, "status": "published",
    "telegram_message_id": 99999, "paynow_player_id": None, "created_at": _TS,
}
_VENUE_ROW = {
    "id": _VENUE_ID, "name": "Fengshan CC",
    "court_cost_per_hour": 15.0, "default_pub_fee": 12.0, "created_at": _TS,
}
_ROSTER_ROW = {
    "id": _ENTRY_ID, "session_id": _SESSION_ID,
    "player_id": None, "guest_name": "Alice", "player_type": "guest",
    "payment_status": "verified_paid", "is_waitlisted": False, "position": 1,
    "joined_at": _TS, "created_at": _TS,
}
_FUND_ENTRY_ROW = {
    "id": _FUND_ID, "description": "Opening balance", "amount": 200.0, "created_at": _TS,
}


def _make_mock_db():
    """Build a mock DB client where all chain methods return the same builder."""
    client = MagicMock()
    builder = MagicMock()
    for method in ("select", "insert", "update", "delete", "eq", "order",
                   "limit", "maybe_single", "in_"):
        getattr(builder, method).return_value = builder
    client.table.return_value = builder
    client.rpc.return_value = builder
    return client, builder


def _make_client(db_responses: list):
    """Generator yielding a TestClient with DB mocked and auth bypassed."""
    from app.main import app
    from app.dependencies import require_admin

    mock_client, mock_builder = _make_mock_db()
    mock_builder.execute.side_effect = [
        MagicMock(data=r) for r in db_responses
    ]

    app.dependency_overrides[require_admin] = lambda: "test-admin"

    try:
        with (
            patch("app.db.client._service_client", mock_client),
            patch("app.bot.runner.bot_runner.build"),
            patch("app.bot.runner.bot_runner.start_polling", new_callable=AsyncMock),
            patch("app.bot.runner.bot_runner.post_recruit_message", new=AsyncMock()),
            patch("app.bot.runner.bot_runner.delete_session_message", new=AsyncMock()),
        ):
            with TestClient(app, raise_server_exceptions=True) as client:
                yield client
    finally:
        app.dependency_overrides.clear()


# ── Feature 4: POST /sessions/{id}/recruit ────────────────────────────────────

def test_recruit_endpoint_returns_formatted_message():
    """POST /recruit returns a message containing slots, venue, shuttle line."""
    import contextlib

    # session_service.get_by_id needs roster_entries + shuttle_usage nested
    session_row_with_roster = {
        **_SESSION_ROW,
        "roster_entries": [dict(_ROSTER_ROW)],
        "shuttle_usage": [],
    }
    db_responses = [
        [session_row_with_roster],  # session_service.get_by_id
        [_VENUE_ROW],               # venue_service.get_by_id
        [_ROSTER_ROW],              # roster_service.get_session_roster
    ]

    with contextlib.contextmanager(_make_client)(db_responses) as client:
        resp = client.post(f"/api/v1/sessions/{_SESSION_ID}/recruit")

    assert resp.status_code == 200
    body = resp.json()
    assert "message" in body
    msg = body["message"]
    assert "Fengshan CC" in msg
    assert "RSL Ultimate shuttles provided" in msg
    assert "[" in msg and "slot" in msg


# ── Feature 3: Fund entries endpoint ─────────────────────────────────────────

def test_fund_create_entry_endpoint():
    """POST /fund/entries creates an entry and returns it."""
    import contextlib

    db_responses = [[_FUND_ENTRY_ROW]]  # insert response

    with contextlib.contextmanager(_make_client)(db_responses) as client:
        resp = client.post("/api/v1/fund/entries", json={"description": "Opening balance", "amount": 200.0})

    assert resp.status_code == 201
    body = resp.json()
    assert body["description"] == "Opening balance"
    assert body["amount"] == pytest.approx(200.0)


def test_fund_balance_endpoint():
    """GET /fund/balance returns entries_total summing all entries."""
    import contextlib

    rows = [
        {"id": _FUND_ID, "description": "Opening", "amount": 200.0, "created_at": _TS},
        {"id": "ffffffff-ffff-ffff-ffff-ffffffffffff", "description": "Shuttles", "amount": -40.0, "created_at": _TS},
    ]
    db_responses = [rows]  # get_entries → order query

    with contextlib.contextmanager(_make_client)(db_responses) as client:
        resp = client.get("/api/v1/fund/balance")

    assert resp.status_code == 200
    body = resp.json()
    assert body["entries_total"] == pytest.approx(160.0)


# ── Feature 5: delete_session_message on complete ────────────────────────────

@pytest.mark.asyncio
async def test_delete_session_message_calls_bot_delete():
    """BotRunner.delete_session_message calls bot.delete_message with the stored message_id."""
    from app.bot.runner import BotRunner
    from app.models.session import Session
    from datetime import date, time

    runner = BotRunner()
    runner._app = MagicMock()
    runner._app.bot.delete_message = AsyncMock()

    session = Session(
        id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        venue_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        date=date(2026, 5, 31), start_time=time(20, 0), end_time=time(22, 0),
        duration_hours=2.0, courts_booked="C1", num_courts=1,
        min_skill_level="HB", max_skill_level="LI",
        pub_fee=12.0, max_pax=12, status="completed",
        telegram_message_id=987654,
        created_at=datetime.now(timezone.utc),
    )
    await runner.delete_session_message(session)

    runner._app.bot.delete_message.assert_called_once()
    assert runner._app.bot.delete_message.call_args.kwargs["message_id"] == 987654


@pytest.mark.asyncio
async def test_delete_session_message_noop_if_no_telegram_id():
    from app.bot.runner import BotRunner
    from app.models.session import Session
    from datetime import date, time

    runner = BotRunner()
    runner._app = MagicMock()
    runner._app.bot.delete_message = AsyncMock()

    session = Session(
        id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        venue_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        date=date(2026, 5, 31), start_time=time(20, 0), end_time=time(22, 0),
        duration_hours=2.0, courts_booked="C1", num_courts=1,
        min_skill_level="HB", max_skill_level="LI",
        pub_fee=12.0, max_pax=12, status="completed",
        telegram_message_id=None,
        created_at=datetime.now(timezone.utc),
    )
    await runner.delete_session_message(session)

    runner._app.bot.delete_message.assert_not_called()


# ── Cross-service: shuttle auto-deducts fund ─────────────────────────────────

def test_shuttle_create_auto_deducts_fund_entry():
    """Creating a batch (remaining_count>0) inserts a negative fund entry for purchase cost."""
    import app.services.shuttle_service as shuttle_service
    from app.models.shuttle import ShuttleBatchCreate
    from datetime import datetime, timezone

    batch_row = {
        "id": "aabbccdd-aabb-aabb-aabb-aabbccddaabb", "batch_name": "RSL May", "brand": "RSL Ultimate",
        "owner_label": None, "cost_per_tube": 20.0, "shuttles_per_tube": 12,
        "cost_per_shuttle": 1.67, "remaining_count": 24, "is_active": True,
        "purchased_at": None, "created_at": datetime.now(timezone.utc).isoformat(),
    }
    client = MagicMock()
    client.table.return_value.insert.return_value.execute.return_value.data = [batch_row]

    with (
        patch("app.services.shuttle_service.get_service_client", return_value=client),
        patch("app.services.shuttle_service.fund_service.add_entry") as mock_add,
    ):
        shuttle_service.create(ShuttleBatchCreate(
            batch_name="RSL May", brand="RSL Ultimate",
            cost_per_tube=20.0, shuttles_per_tube=12, remaining_count=24,
        ))

    mock_add.assert_called_once()
    entry_arg = mock_add.call_args[0][0]
    assert entry_arg.amount == pytest.approx(-40.0)  # ceil(24/12) * $20 = $40
    assert "RSL May" in entry_arg.description


def test_shuttle_create_zero_count_does_not_deduct_fund():
    """Creating a batch with remaining_count=0 skips the fund deduction."""
    import app.services.shuttle_service as shuttle_service
    from app.models.shuttle import ShuttleBatchCreate
    from datetime import datetime, timezone

    batch_row = {
        "id": "aabbccdd-aabb-aabb-aabb-aabbccddaabb", "batch_name": "Empty", "brand": "Yonex",
        "owner_label": None, "cost_per_tube": 20.0, "shuttles_per_tube": 12,
        "cost_per_shuttle": 1.67, "remaining_count": 0, "is_active": True,
        "purchased_at": None, "created_at": datetime.now(timezone.utc).isoformat(),
    }
    client = MagicMock()
    client.table.return_value.insert.return_value.execute.return_value.data = [batch_row]

    with (
        patch("app.services.shuttle_service.get_service_client", return_value=client),
        patch("app.services.shuttle_service.fund_service.add_entry") as mock_add,
    ):
        shuttle_service.create(ShuttleBatchCreate(
            batch_name="Empty", brand="Yonex",
            cost_per_tube=20.0, shuttles_per_tube=12, remaining_count=0,
        ))

    mock_add.assert_not_called()
