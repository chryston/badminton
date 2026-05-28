from datetime import datetime, timezone
from uuid import UUID
from app.db.client import get_service_client
from app.models.player import PlayerCreate
from app.models.roster import RosterEntry
import app.services.player_service as player_service


def get_session_roster(session_id: UUID) -> list[RosterEntry]:
    client = get_service_client()
    result = (
        client.table("roster_entries")
        .select("*")
        .eq("session_id", str(session_id))
        .order("position")
        .execute()
    )
    return [RosterEntry(**row) for row in result.data]


def get_active_count(session_id: UUID) -> int:
    client = get_service_client()
    result = (
        client.table("roster_entries")
        .select("id")
        .eq("session_id", str(session_id))
        .eq("is_waitlisted", False)
        .execute()
    )
    return len(result.data)


def promote_from_waitlist(session_id: UUID) -> RosterEntry | None:
    client = get_service_client()
    result = (
        client.table("roster_entries")
        .select("*")
        .eq("session_id", str(session_id))
        .eq("is_waitlisted", True)
        .order("position")
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    entry_id = result.data[0]["id"]
    updated = (
        client.table("roster_entries")
        .update({"is_waitlisted": False})
        .eq("id", entry_id)
        .execute()
    )
    return RosterEntry(**updated.data[0])


def add_player(
    session_id: UUID, telegram_id: int, player_name: str
) -> tuple[RosterEntry, bool]:
    """Add a player by telegram_id, creating a player record if needed.
    Returns (entry, is_waitlisted).
    """
    client = get_service_client()

    # Fetch session to check capacity
    session_result = (
        client.table("sessions").select("max_pax").eq("id", str(session_id)).execute()
    )
    if not session_result.data:
        raise ValueError(f"Session {session_id} not found")
    max_pax = session_result.data[0]["max_pax"]

    # Find or create player
    player = player_service.get_by_telegram_id(telegram_id)
    if player is None:
        player = player_service.create(
            PlayerCreate(name=player_name, is_internal=False, telegram_id=telegram_id)
        )

    # Check if player already on roster
    existing = (
        client.table("roster_entries")
        .select("id")
        .eq("session_id", str(session_id))
        .eq("player_id", str(player.id))
        .execute()
    )
    if existing.data:
        raise ValueError("Player is already on the roster for this session")

    active_count = get_active_count(session_id)
    is_waitlisted = active_count >= max_pax

    # Determine next position across all entries
    all_entries = (
        client.table("roster_entries")
        .select("position")
        .eq("session_id", str(session_id))
        .order("position", desc=True)
        .limit(1)
        .execute()
    )
    next_position = (all_entries.data[0]["position"] + 1) if all_entries.data else 1

    now = datetime.now(timezone.utc).isoformat()
    row = {
        "session_id": str(session_id),
        "player_id": str(player.id),
        "player_type": "registered",
        "payment_status": "verified_paid" if player.is_internal else "unpaid",
        "is_waitlisted": is_waitlisted,
        "position": next_position,
        "joined_at": now,
    }
    result = client.table("roster_entries").insert(row).execute()
    entry = RosterEntry(**result.data[0])
    return entry, is_waitlisted


def add_guest(session_id: UUID, guest_name: str) -> RosterEntry:
    """Manually add an external (guest) player to the roster."""
    client = get_service_client()

    session_result = (
        client.table("sessions").select("max_pax").eq("id", str(session_id)).execute()
    )
    if not session_result.data:
        raise ValueError(f"Session {session_id} not found")
    max_pax = session_result.data[0]["max_pax"]

    active_count = get_active_count(session_id)
    is_waitlisted = active_count >= max_pax

    all_entries = (
        client.table("roster_entries")
        .select("position")
        .eq("session_id", str(session_id))
        .order("position", desc=True)
        .limit(1)
        .execute()
    )
    next_position = (all_entries.data[0]["position"] + 1) if all_entries.data else 1

    now = datetime.now(timezone.utc).isoformat()
    row = {
        "session_id": str(session_id),
        "guest_name": guest_name,
        "player_type": "guest",
        "payment_status": "unpaid",
        "is_waitlisted": is_waitlisted,
        "position": next_position,
        "joined_at": now,
    }
    result = client.table("roster_entries").insert(row).execute()
    return RosterEntry(**result.data[0])


def remove_entry(entry_id: UUID) -> RosterEntry | None:
    """Remove a roster entry, re-number remaining positions, and promote from waitlist if needed."""
    client = get_service_client()

    result = (
        client.table("roster_entries").select("*").eq("id", str(entry_id)).execute()
    )
    if not result.data:
        return None
    removed = RosterEntry(**result.data[0])

    client.table("roster_entries").delete().eq("id", str(entry_id)).execute()

    # Decrement positions of all non-waitlisted entries that came after the removed one
    client.rpc(
        "decrement_positions_after",
        {"p_session_id": str(removed.session_id), "p_position": removed.position},
    ).execute()

    # If the removed entry was active, promote first waitlisted player
    if not removed.is_waitlisted:
        promote_from_waitlist(removed.session_id)

    return removed


def verify_payment(entry_id: UUID) -> RosterEntry:
    client = get_service_client()
    result = (
        client.table("roster_entries")
        .update({"payment_status": "verified_paid"})
        .eq("id", str(entry_id))
        .execute()
    )
    if not result.data:
        raise ValueError(f"RosterEntry {entry_id} not found")
    return RosterEntry(**result.data[0])
