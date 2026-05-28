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
        f"🏟️ {session.courts_booked}",
        _skill_range_label(session.min_skill_level, session.max_skill_level),
        f"💰 Fee: ${session.pub_fee:.0f} per pax",
        f"👤 Max: {session.max_pax} players",
        "",
        f"💳 Transfer to: {paynow_name} ({paynow_phone})",
        "",
        f"Players ({active_count}/{session.max_pax}):",
    ]

    for i, entry in enumerate(active, 1):
        name = _entry_display_name(entry, player_names)
        paid_label = " (paid)" if entry.payment_status == "verified_paid" else ""
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


def format_cancellation_message(session: Session, venue_name: str, reason: str) -> str:
    """Format a cancellation notice for the LOWKEY group."""
    date_str = session.date.strftime("%a, %d %b %Y")
    time_str = f"{session.start_time.strftime('%H:%M')} - {session.end_time.strftime('%H:%M')}"
    return "\n".join([
        "❌ Session Cancelled",
        f"📅 {date_str} {time_str} · {venue_name}",
        f"Reason: {reason}",
        "Sorry for the inconvenience! 🙏",
    ])


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


def _entry_display_name(entry: RosterEntry, player_names: dict[UUID, str]) -> str:
    if entry.guest_name:
        return entry.guest_name
    if entry.player_id and entry.player_id in player_names:
        return player_names[entry.player_id]
    return "Unknown"


def _skill_range_label(min_level: str, max_level: str) -> str:
    if min_level == max_level:
        return f"🎯 Level: {min_level}"
    return f"🎯 Level: {min_level} – {max_level}"


def format_withdraw_notification(
    player_name: str,
    session: Session,
    venue_name: str,
    was_paid: bool,
) -> str:
    """Format an admin-group notification when a player withdraws."""
    date_str = session.date.strftime("%a, %d %b %Y")
    time_str = f"{session.start_time.strftime('%H:%M')} – {session.end_time.strftime('%H:%M')}"
    pay_line = "⚠️ They had PAID — please return their money. 💸" if was_paid else "They had not paid."
    return "\n".join([
        f"🚪 {player_name} has withdrawn from the session.",
        f"📅 {date_str} {time_str} · {venue_name}",
        pay_line,
    ])


def format_help_text() -> str:
    """Player-facing /help guide."""
    return "\n".join([
        "🏸 Badminton Bot — Help",
        "",
        "▶️ To join a game:",
        "  Press [Join ✋] on any session post in the group.",
        "",
        "🚪 To leave a game:",
        "  Press [Leave 🚪] on the same session post.",
        "",
        "💳 To pay:",
        "  PayNow to the details shown in the session post.",
        "  Send your payment screenshot to an admin.",
        "  Admin will mark you as ✅ paid once confirmed.",
        "",
        "❓ Need help? Message an admin directly.",
    ])


def format_recruit_message(session: Session, slots_left: int, venue_name: str) -> str:
    """Format a player-recruitment post for the admin group."""
    date_str = session.date.strftime("%d %b %Y, %a")
    start_str = session.start_time.strftime("%I:%M %p").lstrip("0")
    end_str = session.end_time.strftime("%I:%M %p").lstrip("0")
    if session.min_skill_level == session.max_skill_level:
        skill_str = session.min_skill_level
    else:
        skill_str = f"{session.min_skill_level} – {session.max_skill_level}"
    slot_label = f"[{slots_left} slot{'s' if slots_left != 1 else ''} left]"
    court_label = f"{session.num_courts} court{'s' if session.num_courts != 1 else ''}"
    return "\n".join([
        "Looking for friendly players to join the following game:",
        "",
        slot_label,
        f"Date: {date_str}",
        f"Time: {start_str} – {end_str}",
        f"Venue: {venue_name}",
        f"Level: {skill_str}",
        f"Cost: ${session.pub_fee:.0f} per pax",
        f"Max {session.max_pax} pax, ({court_label})",
        "RSL Ultimate shuttles provided",
        "",
        "PM if interested, thank you!",
    ])


def build_join_leave_buttons(session_id: str, is_full: bool) -> InlineKeyboardMarkup:
    """Build inline keyboard with Join (or Full) and Leave buttons."""
    join_btn = (
        InlineKeyboardButton("Full 🔒", callback_data="full")
        if is_full
        else InlineKeyboardButton("Join ✋", callback_data=f"join:{session_id}")
    )
    leave_btn = InlineKeyboardButton("Leave 🚪", callback_data=f"leave:{session_id}")
    return InlineKeyboardMarkup([[join_btn, leave_btn]])
