from uuid import UUID

from app.db.client import get_service_client
from app.models.court_slot import CourtSlot, CourtSlotCreate


def get_by_session(session_id: UUID) -> list[CourtSlot]:
    client = get_service_client()
    result = (
        client.table("court_slots")
        .select("*")
        .eq("session_id", str(session_id))
        .execute()
    )
    return [CourtSlot(**row) for row in result.data]


def add_slot(session_id: UUID, data: CourtSlotCreate) -> CourtSlot:
    client = get_service_client()
    payload = {
        "session_id": str(session_id),
        "court_label": data.court_label,
        "from_time": data.from_time.strftime("%H:%M:%S"),
        "to_time": data.to_time.strftime("%H:%M:%S"),
        "booker_player_id": str(data.booker_player_id),
    }
    result = client.table("court_slots").insert(payload).execute()
    return CourtSlot(**result.data[0])


def remove_slot(slot_id: UUID) -> None:
    client = get_service_client()
    client.table("court_slots").delete().eq("id", str(slot_id)).execute()
