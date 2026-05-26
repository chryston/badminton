"""Unit tests for pnl_service.calculate() — pure function, no mocks needed."""
from collections import defaultdict
from datetime import date, time, datetime, timezone
from uuid import UUID, uuid4

import pytest

from app.models.court_slot import CourtSlot
from app.models.roster import RosterEntry
from app.models.session import SessionWithRoster
from app.models.shuttle import ShuttleBatch, ShuttleUsage
from app.services.pnl_service import calculate

_SESSION_ID = uuid4()
_VENUE_ID = uuid4()
_BATCH_ID = uuid4()
_BOOKER_ID = uuid4()
_NOW = datetime.now(timezone.utc)


def _session(roster=None, shuttle_usage=None, pub_fee=10.0) -> SessionWithRoster:
    r = roster or []
    su = shuttle_usage or []
    return SessionWithRoster(
        id=_SESSION_ID,
        venue_id=_VENUE_ID,
        date=date(2025, 6, 15),
        start_time=time(9, 0),
        end_time=time(11, 0),
        duration_hours=2.0,
        courts_booked="Court 1",
        num_courts=1,
        min_skill_level="HB",
        max_skill_level="LI",
        pub_fee=pub_fee,
        max_pax=12,
        status="completed",
        created_at=_NOW,
        roster=r,
        shuttle_usage=su,
        active_count=sum(1 for e in r if not e.is_waitlisted),
        waitlist_count=sum(1 for e in r if e.is_waitlisted),
    )


def _entry(
    payment_status="verified_paid",
    is_waitlisted=False,
    player_id=None,
    position=1,
) -> RosterEntry:
    return RosterEntry(
        id=uuid4(),
        session_id=_SESSION_ID,
        player_id=player_id,
        player_type="registered" if player_id else "guest",
        payment_status=payment_status,
        is_waitlisted=is_waitlisted,
        position=position,
        joined_at=_NOW,
        created_at=_NOW,
    )


def _court_slot(from_hour: int = 9, to_hour: int = 11) -> CourtSlot:
    """One slot covering from_hour to to_hour on the session date."""
    return CourtSlot(
        id=uuid4(),
        session_id=_SESSION_ID,
        court_label="Court 1",
        from_time=time(from_hour, 0),
        to_time=time(to_hour, 0),
        booker_player_id=_BOOKER_ID,
        created_at=_NOW,
    )


def _calc(session, slots=None, **kwargs):
    """Helper: call calculate() with sensible defaults."""
    return calculate(
        session,
        shuttle_batches=kwargs.get("shuttle_batches", {}),
        court_cost_per_hour=kwargs.get("court_cost_per_hour", 15.0),
        court_slots=slots if slots is not None else [_court_slot()],
        booker_names=kwargs.get("booker_names", {_BOOKER_ID: "Belle"}),
        internal_player_ids=kwargs.get("internal_player_ids", None),
    )


def test_calculate_basic_profit():
    """5 paying external players × $10 = $50 income, $30 court cost = $20 profit."""
    roster = [_entry() for _ in range(5)]
    result = _calc(_session(roster=roster))
    assert result.net == 20.0


def test_calculate_income_calculation():
    """total_fees_collected and external_paid_count from verified_paid active entries."""
    roster = [_entry() for _ in range(5)]
    result = _calc(_session(roster=roster))
    assert result.total_fees_collected == 50.0
    assert result.external_paid_count == 5


def test_calculate_cost_breakdown():
    """court_cost = slot duration × rate; no shuttles = zero shuttle_cost."""
    roster = [_entry() for _ in range(5)]
    result = _calc(_session(roster=roster))
    assert result.court_cost == 30.0   # 2h × $15
    assert result.shuttle_cost == 0.0


def test_calculate_excludes_internal_players():
    """Internal players do not contribute to fee income."""
    internal_id_1 = uuid4()
    internal_id_2 = uuid4()
    roster = [
        _entry(player_id=uuid4()),
        _entry(player_id=uuid4()),
        _entry(player_id=uuid4()),
        _entry(player_id=internal_id_1),
        _entry(player_id=internal_id_2),
    ]
    result = _calc(
        _session(roster=roster),
        internal_player_ids={internal_id_1, internal_id_2},
    )
    assert result.total_fees_collected == 30.0
    assert result.external_paid_count == 3
    assert result.total_roster_count == 5


def test_calculate_excludes_waitlisted():
    """Waitlisted players do not contribute to income."""
    roster = [
        _entry(position=1),
        _entry(position=2),
        _entry(payment_status="verified_paid", is_waitlisted=True, position=3),
    ]
    result = _calc(_session(roster=roster))
    assert result.total_fees_collected == 20.0
    assert result.external_paid_count == 2


def test_calculate_deficit():
    """Net is negative when costs exceed income."""
    roster = [_entry()]
    result = _calc(_session(roster=roster))
    assert result.total_fees_collected == 10.0
    assert result.net == -20.0


def test_calculate_zero_shuttles():
    """Zero shuttle usage produces zero shuttle_cost."""
    result = _calc(_session())
    assert result.shuttle_cost == 0.0
    assert result.net == -30.0  # 0 income - $30 court


def test_calculate_shuttle_cost():
    """Shuttle cost = count_used × cost_per_shuttle per batch."""
    batch = ShuttleBatch(
        id=_BATCH_ID,
        batch_name="RSL Sonic 6",
        brand="RSL",
        cost_per_tube=20.0,
        shuttles_per_tube=12,
        cost_per_shuttle=20.0 / 12,
        remaining_count=50,
        is_active=True,
        created_at=_NOW,
    )
    usage = ShuttleUsage(
        id=uuid4(),
        session_id=_SESSION_ID,
        batch_id=_BATCH_ID,
        count_used=6,
        created_at=_NOW,
    )
    roster = [_entry() for _ in range(5)]
    result = _calc(
        _session(roster=roster, shuttle_usage=[usage]),
        shuttle_batches={_BATCH_ID: batch},
    )
    expected_shuttle = 6 * (20.0 / 12)
    assert abs(result.shuttle_cost - expected_shuttle) < 0.001
    assert result.net == pytest.approx(50.0 - 30.0 - expected_shuttle)


def test_calculate_booker_breakdown():
    """booker_breakdown shows each booker's slot cost."""
    booker_a = uuid4()
    booker_b = uuid4()
    slots = [
        CourtSlot(
            id=uuid4(), session_id=_SESSION_ID, court_label="Court 1",
            from_time=time(9, 0), to_time=time(11, 0),
            booker_player_id=booker_a, created_at=_NOW,
        ),
        CourtSlot(
            id=uuid4(), session_id=_SESSION_ID, court_label="Court 2",
            from_time=time(9, 0), to_time=time(10, 0),
            booker_player_id=booker_b, created_at=_NOW,
        ),
    ]
    result = calculate(
        _session(),
        shuttle_batches={},
        court_cost_per_hour=15.0,
        court_slots=slots,
        booker_names={booker_a: "Alice", booker_b: "Bob"},
    )
    breakdown = {b.player_name: b.amount for b in result.booker_breakdown}
    assert breakdown["Alice"] == 30.0   # 2h × $15
    assert breakdown["Bob"] == 15.0     # 1h × $15
    assert result.court_cost == 45.0
