"""Unit tests for bot/message_formatter.py — pure functions, no mocks needed."""
from datetime import date, time, datetime, timezone
from uuid import UUID, uuid4

from app.bot.message_formatter import format_session_announcement, build_join_button
from app.models.session import Session
from app.models.roster import RosterEntry

_NOW = datetime.now(timezone.utc)
_SESSION_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_VENUE_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


def _session(max_pax=12) -> Session:
    return Session(
        id=_SESSION_ID,
        venue_id=_VENUE_ID,
        date=date(2025, 6, 15),
        start_time=time(9, 0),
        end_time=time(11, 0),
        courts_booked="1",
        num_courts=1,
        skill_level="HB - LI",
        pub_fee=10.0,
        max_pax=max_pax,
        status="published",
        created_at=_NOW,
    )


def _entry(player_id=None, guest_name=None, payment_status="unpaid", is_waitlisted=False, position=1) -> RosterEntry:
    return RosterEntry(
        id=uuid4(),
        session_id=_SESSION_ID,
        player_id=player_id,
        guest_name=guest_name,
        player_type="registered" if player_id else "guest",
        payment_status=payment_status,
        is_waitlisted=is_waitlisted,
        position=position,
        joined_at=_NOW,
        created_at=_NOW,
    )


def test_format_announcement_shows_numbered_players():
    """Active players appear as '1. Alice', '2. Bob'."""
    alice_id = uuid4()
    bob_id = uuid4()
    roster = [
        _entry(player_id=alice_id, position=1),
        _entry(player_id=bob_id, position=2),
    ]
    player_names = {alice_id: "Alice", bob_id: "Bob"}

    text = format_session_announcement(
        _session(), roster, player_names,
        venue_name="Test Hall", paynow_name="Admin", paynow_phone="91234567",
    )

    assert "1. Alice" in text
    assert "2. Bob" in text


def test_format_announcement_paid_label():
    """verified_paid entry shows '(paid)' suffix."""
    player_id = uuid4()
    roster = [_entry(player_id=player_id, payment_status="verified_paid", position=1)]
    player_names = {player_id: "Alice"}

    text = format_session_announcement(
        _session(), roster, player_names,
        venue_name="Test Hall", paynow_name="Admin", paynow_phone="91234567",
    )

    assert "1. Alice (paid)" in text


def test_format_announcement_hides_waitlist_when_empty():
    """Waitlist section absent when no waitlisted entries."""
    player_id = uuid4()
    roster = [_entry(player_id=player_id, position=1)]
    player_names = {player_id: "Alice"}

    text = format_session_announcement(
        _session(), roster, player_names,
        venue_name="Test Hall", paynow_name="Admin", paynow_phone="91234567",
    )

    assert "Waitlist:" not in text


def test_format_announcement_shows_waitlist_when_present():
    """Waitlist section present with 'W1. Charlie' format."""
    alice_id = uuid4()
    charlie_id = uuid4()
    roster = [
        _entry(player_id=alice_id, is_waitlisted=False, position=1),
        _entry(player_id=charlie_id, is_waitlisted=True, position=2),
    ]
    player_names = {alice_id: "Alice", charlie_id: "Charlie"}

    text = format_session_announcement(
        _session(), roster, player_names,
        venue_name="Test Hall", paynow_name="Admin", paynow_phone="91234567",
    )

    assert "Waitlist:" in text
    assert "W1. Charlie" in text


def test_format_announcement_shows_full_count():
    """'Players (3/12)' shows active count and max_pax."""
    roster = [
        _entry(guest_name=f"Player {i}", position=i)
        for i in range(1, 4)
    ]

    text = format_session_announcement(
        _session(max_pax=12), roster, {},
        venue_name="Test Hall", paynow_name="Admin", paynow_phone="91234567",
    )

    assert "Players (3/12):" in text


def test_join_button_callback_data():
    """Join button callback_data is 'join:{session_id}'."""
    session_id = "test-session-123"
    markup = build_join_button(session_id)

    button = markup.inline_keyboard[0][0]
    assert button.callback_data == f"join:{session_id}"
