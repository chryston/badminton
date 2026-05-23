from uuid import UUID

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.models.roster import RosterEntry
from app.models.session import Session


def format_session_announcement(
    session: Session,
    roster: list[RosterEntry],
    player_names: dict[UUID, str],
    venue_name: str,
    paynow_name: str,
    paynow_phone: str,
) -> str:
    """Format the main LOWKEY group announcement message.

    player_names maps player_id -> display name for registered players.
    Caller is responsible for resolving these before calling.
    Plain text (no Markdown parse_mode) to avoid breakage from player/venue names
    containing special characters.
    """
    active = [e for e in roster if not e.is_waitlisted]
    waitlisted = [e for e in roster if e.is_waitlisted]
    active_count = len(active)

    date_str = session.date.strftime("%a, %d %b %Y")
    time_str = f"{session.start_time.strftime('%H:%M')} - {session.end_time.strftime('%H:%M')}"

    lines = [
        "🏸 Badminton Session",
        f"📅 {date_str} {time_str}",
        f"📍 {venue_name}",
        f"🏟️ Courts: {session.courts_booked}",
        f"🎯 Level: {session.skill_level}",
        f"💰 Fee: ${session.pub_fee:.0f} per pax",
        f"👤 Max: {session.max_pax} players",
        "",
        f"💳 Transfer to: {paynow_name} ({paynow_phone})",
        "",
        f"Players ({active_count}/{session.max_pax}):",
    ]

    for i, entry in enumerate(active, 1):
        name = _entry_display_name(entry, player_names)
        paid_label = " ✅" if entry.payment_status == "verified_paid" else ""
        lines.append(f"{i}. {name}{paid_label}")

    if active_count >= session.max_pax:
        lines.append("")
        lines.append("Full 🔒")

    if waitlisted:
        lines.append("")
        lines.append("Waitlist:")
        for i, entry in enumerate(waitlisted, 1):
            name = _entry_display_name(entry, player_names)
            lines.append(f"W{i}. {name}")

    return "\n".join(lines)


def format_admin_summary(session: Session, venue_name: str) -> str:
    """Format the admin group summary after posting."""
    date_str = session.date.strftime("%a, %d %b %Y")
    time_str = f"{session.start_time.strftime('%H:%M')} - {session.end_time.strftime('%H:%M')}"
    short_id = str(session.id)[:8]
    return (
        f"📌 Posted to LOWKEY\n"
        f"Date: {date_str} {time_str} | {venue_name}\n"
        f"Session ID: {session.id} (short: {short_id})"
    )


def build_join_button(session_id: str) -> InlineKeyboardMarkup:
    """Build inline keyboard with Join button. CallbackData: 'join:{session_id}'."""
    keyboard = [[InlineKeyboardButton("Join ✋", callback_data=f"join:{session_id}")]]
    return InlineKeyboardMarkup(keyboard)


def build_full_button() -> InlineKeyboardMarkup:
    """Build keyboard showing session is full (non-functional button)."""
    keyboard = [[InlineKeyboardButton("Full 🔒", callback_data="full")]]
    return InlineKeyboardMarkup(keyboard)


def _entry_display_name(entry: RosterEntry, player_names: dict[UUID, str]) -> str:
    if entry.guest_name:
        return entry.guest_name
    if entry.player_id and entry.player_id in player_names:
        return player_names[entry.player_id]
    return "Unknown"
