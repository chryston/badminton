from uuid import UUID
from app.db.client import get_service_client
from app.models.player import Player, PlayerCreate, PlayerUpdate


def get_by_id(player_id: UUID) -> Player:
    client = get_service_client()
    result = client.table("players").select("*").eq("id", str(player_id)).execute()
    if not result.data:
        raise ValueError(f"Player {player_id} not found")
    return Player(**result.data[0])


def get_all() -> list[Player]:
    client = get_service_client()
    result = client.table("players").select("*").order("name").execute()
    return [Player(**row) for row in result.data]


def get_by_telegram_id(telegram_id: int) -> Player | None:
    client = get_service_client()
    result = client.table("players").select("*").eq("telegram_id", telegram_id).execute()
    if not result.data:
        return None
    return Player(**result.data[0])


def get_internal_players() -> list[Player]:
    client = get_service_client()
    result = (
        client.table("players").select("*").eq("is_internal", True).order("name").execute()
    )
    return [Player(**row) for row in result.data]


def create(data: PlayerCreate) -> Player:
    client = get_service_client()
    result = client.table("players").insert(data.model_dump(exclude_none=True)).execute()
    return Player(**result.data[0])


def update(player_id: UUID, data: PlayerUpdate) -> Player:
    client = get_service_client()
    payload = data.model_dump(exclude_none=True)
    if not payload:
        raise ValueError("No fields to update")
    result = (
        client.table("players").update(payload).eq("id", str(player_id)).execute()
    )
    if not result.data:
        raise ValueError(f"Player {player_id} not found")
    return Player(**result.data[0])


def set_telegram_id(player_id: UUID, telegram_id: int) -> Player:
    client = get_service_client()
    result = (
        client.table("players")
        .update({"telegram_id": telegram_id})
        .eq("id", str(player_id))
        .execute()
    )
    if not result.data:
        raise ValueError(f"Player {player_id} not found")
    return Player(**result.data[0])
