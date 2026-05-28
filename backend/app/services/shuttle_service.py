import logging
import math
from uuid import UUID

import app.services.fund_service as fund_service
from app.db.client import get_service_client
from app.models.fund import FundEntryCreate
from app.models.shuttle import ShuttleBatch, ShuttleBatchCreate, ShuttleBatchUpdate


def get_all() -> list[ShuttleBatch]:
    client = get_service_client()
    result = client.table("shuttle_batches").select("*").order("created_at", desc=True).execute()
    return [ShuttleBatch(**row) for row in result.data]


def get_by_id(batch_id: UUID) -> ShuttleBatch:
    client = get_service_client()
    result = client.table("shuttle_batches").select("*").eq("id", str(batch_id)).execute()
    if not result.data:
        raise ValueError(f"ShuttleBatch {batch_id} not found")
    return ShuttleBatch(**result.data[0])


def get_active() -> list[ShuttleBatch]:
    client = get_service_client()
    result = (
        client.table("shuttle_batches")
        .select("*")
        .eq("is_active", True)
        .order("created_at", desc=True)
        .execute()
    )
    return [ShuttleBatch(**row) for row in result.data]


def create(data: ShuttleBatchCreate) -> ShuttleBatch:
    client = get_service_client()
    result = (
        client.table("shuttle_batches")
        .insert(data.model_dump(mode="json", exclude_none=True))
        .execute()
    )
    batch = ShuttleBatch(**result.data[0])

    # Auto-record shuttle purchase cost in fund ledger (skip if no shuttles in batch).
    if batch.remaining_count > 0:
        tubes = math.ceil(batch.remaining_count / batch.shuttles_per_tube)
        purchase_cost = round(tubes * batch.cost_per_tube, 2)
        try:
            fund_service.add_entry(FundEntryCreate(
                description=f"Shuttle batch: {batch.batch_name} ({batch.brand})",
                amount=-purchase_cost,
            ))
        except Exception:
            logging.getLogger(__name__).warning(
                "Failed to record fund entry for shuttle batch %s", batch.id
            )

    return batch


def update(batch_id: UUID, data: ShuttleBatchUpdate) -> ShuttleBatch:
    client = get_service_client()
    payload = data.model_dump(mode="json", exclude_none=True)
    if not payload:
        raise ValueError("No fields to update")
    result = (
        client.table("shuttle_batches").update(payload).eq("id", str(batch_id)).execute()
    )
    if not result.data:
        raise ValueError(f"ShuttleBatch {batch_id} not found")
    return ShuttleBatch(**result.data[0])


def deduct(batch_id: UUID, count: int) -> ShuttleBatch:
    """Decrement remaining_count by count. Raises ValueError if insufficient stock."""
    client = get_service_client()
    result = client.table("shuttle_batches").select("*").eq("id", str(batch_id)).execute()
    if not result.data:
        raise ValueError(f"ShuttleBatch {batch_id} not found")
    batch = ShuttleBatch(**result.data[0])
    if batch.remaining_count < count:
        raise ValueError(
            f"Insufficient shuttles: need {count}, have {batch.remaining_count}"
        )
    new_count = batch.remaining_count - count
    updated = (
        client.table("shuttle_batches")
        .update({"remaining_count": new_count})
        .eq("id", str(batch_id))
        .eq("remaining_count", batch.remaining_count)
        .execute()
    )
    if not updated.data:
        raise ValueError("Concurrent update detected, please retry")
    return ShuttleBatch(**updated.data[0])
