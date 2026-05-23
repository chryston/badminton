"""Unit tests for pnl_service.calculate() — pure function, no mocks needed."""
from datetime import date, time, datetime, timezone
from uuid import UUID, uuid4

from app.services.pnl_service import calculate
from app.models.session import SessionWithRoster
from app.models.roster import RosterEntry
from app.models.shuttle import ShuttleBatch, ShuttleUsage

_SESSION_ID = uuid4()
_VENUE_ID = uuid4()
_BATCH_ID = uuid4()
_NOW = datetime.now(timezone.utc)


def _session(roster=None, shuttle_usage=None, pub_fee=10.0) -> SessionWithRoster:
    r = roster or []
    su = shuttle_usage or []
    return SessionWithRoster(
        id=_SESSION_ID,
        venue_id=_VENUE_ID,
        date=date(2025, 6, 15),
        start_time=time(9, 0),
        end_time=time(11, 0),  # 2 hours
        courts_booked="1",
        num_courts=1,
        skill_level="HB - LI",
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


def test_calculate_basic_profit():
    """Happy path: 5 paying external players × $10 = $50 income, $30 court cost = $20 profit."""
    roster = [_entry() for _ in range(5)]
    result = calculate(_session(roster=roster), shuttle_batches={}, court_cost_per_hour=15.0)

    # 2h × 1 court × $15/hr = $30 court cost; $50 income → $20 net
    assert result.net == 20.0


def test_calculate_income_calculation():
    """total_income and external_paid_count are derived from verified_paid active entries."""
    roster = [_entry() for _ in range(5)]
    result = calculate(_session(roster=roster), shuttle_batches={}, court_cost_per_hour=15.0)

    assert result.total_fees_collected == 50.0
    assert result.external_paid_count == 5


def test_calculate_cost_breakdown():
    """court_cost and shuttle_cost are independently computed."""
    roster = [_entry() for _ in range(5)]
    result = calculate(_session(roster=roster), shuttle_batches={}, court_cost_per_hour=15.0)

    # 2h × 1 court × $15/hr = $30; no shuttles used
    assert result.court_cost == 30.0
    assert result.shuttle_cost == 0.0


def test_calculate_excludes_internal_players():
    """Internal players (auto-paid) are excluded from income calculation."""
    internal_id_1 = uuid4()
    internal_id_2 = uuid4()
    roster = [
        _entry(player_id=uuid4()),
        _entry(player_id=uuid4()),
        _entry(player_id=uuid4()),
        _entry(player_id=internal_id_1),
        _entry(player_id=internal_id_2),
    ]
    result = calculate(
        _session(roster=roster),
        shuttle_batches={},
        court_cost_per_hour=15.0,
        internal_player_ids={internal_id_1, internal_id_2},
    )

    assert result.total_fees_collected == 30.0  # only 3 external × $10
    assert result.external_paid_count == 3
    assert result.total_roster_count == 5


def test_calculate_excludes_waitlisted():
    """Waitlisted players do not contribute to income even if verified_paid."""
    roster = [
        _entry(position=1),
        _entry(position=2),
        _entry(payment_status="verified_paid", is_waitlisted=True, position=3),
    ]
    result = calculate(_session(roster=roster), shuttle_batches={}, court_cost_per_hour=15.0)

    assert result.total_fees_collected == 20.0  # only 2 active players
    assert result.external_paid_count == 2


def test_calculate_deficit():
    """Net can be negative when costs exceed income."""
    roster = [_entry()]  # 1 player × $10 = $10 income
    result = calculate(_session(roster=roster), shuttle_batches={}, court_cost_per_hour=15.0)

    # $10 income - $30 court cost = -$20
    assert result.total_fees_collected == 10.0
    assert result.net == -20.0


def test_calculate_zero_shuttles():
    """Zero shuttle usage results in zero shuttle cost."""
    result = calculate(_session(), shuttle_batches={}, court_cost_per_hour=15.0)

    assert result.shuttle_cost == 0.0
    assert result.net == -30.0  # 0 income - $30 court = -$30


def test_calculate_shuttle_cost():
    """Shuttle cost is count_used × cost_per_shuttle per batch."""
    batch = ShuttleBatch(
        id=_BATCH_ID,
        batch_name="RSL Sonic 6",
        brand="RSL",
        cost_per_tube=20.0,
        shuttles_per_tube=12,
        cost_per_shuttle=20.0 / 12,
        remaining_count=50,
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
    result = calculate(
        _session(roster=roster, shuttle_usage=[usage]),
        shuttle_batches={_BATCH_ID: batch},
        court_cost_per_hour=15.0,
    )

    expected_shuttle_cost = 6 * (20.0 / 12)
    assert abs(result.shuttle_cost - expected_shuttle_cost) < 0.001
    assert result.net == 50.0 - 30.0 - expected_shuttle_cost
