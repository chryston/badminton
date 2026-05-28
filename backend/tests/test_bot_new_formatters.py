"""Behavior tests for new pure formatter functions — no mocks needed."""
from datetime import date, time, datetime, timezone
from uuid import uuid4

import pytest

from app.bot.message_formatter import (
    build_join_leave_buttons,
    format_help_text,
    format_recruit_message,
    format_withdraw_notification,
)
from app.models.session import Session

_NOW = datetime.now(timezone.utc)
_SESSION_ID = uuid4()
_VENUE_ID = uuid4()


def _session(max_pax=12, num_courts=2) -> Session:
    return Session(
        id=_SESSION_ID,
        venue_id=_VENUE_ID,
        date=date(2026, 5, 31),
        start_time=time(20, 0),
        end_time=time(22, 0),
        duration_hours=2.0,
        courts_booked="Court 1 & 2",
        num_courts=num_courts,
        min_skill_level="HB",
        max_skill_level="LI",
        pub_fee=12.0,
        max_pax=max_pax,
        status="published",
        created_at=_NOW,
    )


def test_format_recruit_message_content():
    """recruit message includes slots, venue, fee, courts, shuttle line, and sign-off."""
    msg = format_recruit_message(_session(), slots_left=3, venue_name="Fengshan CC")
    assert "[3 slots left]" in msg
    assert "RSL Ultimate shuttles provided" in msg
    assert "Fengshan CC" in msg
    assert "$12" in msg
    assert "PM if interested" in msg


def test_format_recruit_message_slot_singularity():
    """'slot' (not 'slots') when only 1 slot remains."""
    msg = format_recruit_message(_session(), slots_left=1, venue_name="Fengshan CC")
    assert "[1 slot left]" in msg


def test_format_recruit_message_courts_label():
    """Court count label is singular/plural correctly."""
    assert "1 court" in format_recruit_message(_session(num_courts=1), slots_left=2, venue_name="V")
    assert "2 courts" in format_recruit_message(_session(num_courts=2), slots_left=2, venue_name="V")


def test_format_withdraw_notification_paid_includes_return_warning():
    msg = format_withdraw_notification("Bob", _session(), "Fengshan CC", was_paid=True)
    assert "Bob" in msg
    assert "return" in msg.lower()


def test_format_withdraw_notification_unpaid_no_return_warning():
    msg = format_withdraw_notification("Bob", _session(), "Fengshan CC", was_paid=False)
    assert "Bob" in msg
    assert "return" not in msg.lower()


def test_format_help_text_covers_join_leave_pay():
    msg = format_help_text()
    assert "Join" in msg
    assert "Leave" in msg
    assert "PayNow" in msg


def test_build_join_leave_buttons_not_full_has_join_and_leave():
    kb = build_join_leave_buttons(str(_SESSION_ID), is_full=False)
    buttons = [btn.text for row in kb.inline_keyboard for btn in row]
    assert any("Join" in b for b in buttons)
    assert any("Leave" in b for b in buttons)


def test_build_join_leave_buttons_full_has_full_and_leave():
    kb = build_join_leave_buttons(str(_SESSION_ID), is_full=True)
    buttons = [btn.text for row in kb.inline_keyboard for btn in row]
    assert any("Full" in b for b in buttons)
    assert any("Leave" in b for b in buttons)
