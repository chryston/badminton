from uuid import UUID
from app.db.client import get_service_client
from app.models.venue import Venue


def get_all() -> list[Venue]:
    client = get_service_client()
    result = client.table("venues").select("*").order("name").execute()
    return [Venue(**row) for row in result.data]


def get_by_id(venue_id: UUID) -> Venue:
    client = get_service_client()
    result = client.table("venues").select("*").eq("id", str(venue_id)).execute()
    if not result.data:
        raise ValueError(f"Venue {venue_id} not found")
    return Venue(**result.data[0])
