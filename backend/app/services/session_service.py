from datetime import datetime, timezone
from uuid import UUID
from app.db.client import get_service_client
from app.models.session import Session, SessionCreate, SessionUpdate, SessionWithRoster
from app.models.roster import RosterEntry
from app.models.shuttle import ShuttleUsage, ShuttleUsageCreate
import app.services.shuttle_service as shuttle_service


def get_all() -> list[Session]:
    client = get_service_client()
    result = client.table("sessions").select("*").order("date", desc=True).execute()
    return [Session(**row) for row in result.data]


def get_by_id(session_id: UUID) -> SessionWithRoster:
    client = get_service_client()
    result = (
        client.table("sessions")
        .select("*, roster_entries(*), shuttle_usage(*)")
        .eq("id", str(session_id))
        .execute()
    )
    if not result.data:
        raise ValueError(f"Session {session_id} not found")
    row = result.data[0]
    roster = [RosterEntry(**e) for e in (row.pop("roster_entries", None) or [])]
    usages = [ShuttleUsage(**u) for u in (row.pop("shuttle_usage", None) or [])]
    session = SessionWithRoster(
        **row,
        roster=roster,
        shuttle_usage=usages,
        active_count=sum(1 for e in roster if not e.is_waitlisted),
        waitlist_count=sum(1 for e in roster if e.is_waitlisted),
    )
    return session


def create(data: SessionCreate) -> Session:
    client = get_service_client()
    payload = data.model_dump(mode="json")
    payload["status"] = "internal"
    result = client.table("sessions").insert(payload).execute()
    session = Session(**result.data[0])

    internal_result = (
        client.table("players").select("*").eq("is_internal", True).order("name").execute()
    )
    internal_players = internal_result.data

    if internal_players:
        now = datetime.now(timezone.utc).isoformat()
        roster_rows = [
            {
                "session_id": str(session.id),
                "player_id": player["id"],
                "player_type": "registered",
                "payment_status": "verified_paid",
                "is_waitlisted": False,
                "position": i,
                "joined_at": now,
            }
            for i, player in enumerate(internal_players, 1)
        ]
        client.table("roster_entries").insert(roster_rows).execute()

    return session


def update(session_id: UUID, data: SessionUpdate) -> Session:
    client = get_service_client()
    payload = data.model_dump(mode="json", exclude_none=True)
    if not payload:
        raise ValueError("No fields to update")
    result = (
        client.table("sessions").update(payload).eq("id", str(session_id)).execute()
    )
    if not result.data:
        raise ValueError(f"Session {session_id} not found")
    return Session(**result.data[0])


def publish(session_id: UUID) -> Session:
    client = get_service_client()
    result = (
        client.table("sessions")
        .update({"status": "published"})
        .eq("id", str(session_id))
        .execute()
    )
    if not result.data:
        raise ValueError(f"Session {session_id} not found")
    return Session(**result.data[0])


def complete(session_id: UUID, shuttle_usages: list[ShuttleUsageCreate]) -> SessionWithRoster:
    client = get_service_client()

    # Deduct shuttles from batches first (raises ValueError if insufficient)
    for usage in shuttle_usages:
        shuttle_service.deduct(usage.batch_id, usage.count_used)

    # Insert shuttle_usage rows
    if shuttle_usages:
        usage_rows = [
            {
                "session_id": str(session_id),
                "batch_id": str(u.batch_id),
                "count_used": u.count_used,
            }
            for u in shuttle_usages
        ]
        client.table("shuttle_usage").insert(usage_rows).execute()

    # Mark session completed
    result = (
        client.table("sessions")
        .update({"status": "completed"})
        .eq("id", str(session_id))
        .execute()
    )
    if not result.data:
        raise ValueError(f"Session {session_id} not found")

    return get_by_id(session_id)
