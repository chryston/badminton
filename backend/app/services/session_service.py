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

    max_pax = data.max_pax if data.max_pax is not None else data.num_courts * 6

    session_payload = {
        "venue_id": str(data.venue_id),
        "date": data.date.isoformat(),
        "start_time": data.start_time.strftime("%H:%M:%S"),
        "duration_hours": data.duration_hours,
        "courts_booked": data.courts_booked,
        "num_courts": data.num_courts,
        "min_skill_level": data.min_skill_level,
        "max_skill_level": data.max_skill_level,
        "pub_fee": data.pub_fee,
        "max_pax": max_pax,
        "paynow_player_id": str(data.paynow_player_id) if data.paynow_player_id else None,
    }
    slots_payload = [
        {
            "court_label": slot.court_label,
            "from_time": slot.from_time.strftime("%H:%M:%S"),
            "to_time": slot.to_time.strftime("%H:%M:%S"),
            "booker_player_id": str(slot.booker_player_id),
        }
        for slot in data.court_slots
    ]

    result = client.rpc(
        "create_session_with_slots",
        {"session_data": session_payload, "slots_data": slots_payload},
    ).execute()
    session = Session(**result.data)

    return session


def update(session_id: UUID, data: SessionUpdate) -> Session:
    client = get_service_client()
    payload = data.model_dump(mode="json", exclude_unset=True)
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
    existing = client.table("sessions").select("status").eq("id", str(session_id)).execute()
    if not existing.data:
        raise ValueError(f"Session {session_id} not found")
    if existing.data[0]["status"] != "internal":
        raise ValueError("Session must be in 'internal' status to publish")
    result = (
        client.table("sessions")
        .update({"status": "published"})
        .eq("id", str(session_id))
        .execute()
    )
    return Session(**result.data[0])


def complete(session_id: UUID, shuttle_usages: list[ShuttleUsageCreate]) -> SessionWithRoster:
    client = get_service_client()

    existing = client.table("sessions").select("status").eq("id", str(session_id)).execute()
    if not existing.data:
        raise ValueError(f"Session {session_id} not found")
    if existing.data[0]["status"] != "published":
        raise ValueError("Session must be published before completing")

    # Pre-flight: validate all batches have sufficient stock before touching any
    for usage in shuttle_usages:
        batch = shuttle_service.get_by_id(usage.batch_id)
        if batch.remaining_count < usage.count_used:
            raise ValueError(
                f"Insufficient stock in batch {usage.batch_id}: "
                f"need {usage.count_used}, have {batch.remaining_count}"
            )

    # Safe to deduct now — all checks passed
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


def cancel(session_id: UUID, reason: str) -> Session:
    client = get_service_client()
    existing = client.table("sessions").select("status").eq("id", str(session_id)).execute()
    if not existing.data:
        raise ValueError(f"Session {session_id} not found")
    current_status = existing.data[0]["status"]
    if current_status in ("completed", "cancelled"):
        raise ValueError(f"Cannot cancel a {current_status} session")
    result = (
        client.table("sessions")
        .update({"status": "cancelled", "cancellation_reason": reason})
        .eq("id", str(session_id))
        .execute()
    )
    return Session(**result.data[0])
