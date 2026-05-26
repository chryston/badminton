from collections import defaultdict
from datetime import datetime, timezone
from uuid import UUID

from app.db.client import get_service_client
from app.models.court_slot import CourtSlot
from app.models.roster import BookerReimbursement, PnLResult
from app.models.session import SessionWithRoster
from app.models.shuttle import ShuttleBatch
import app.services.court_slot_service as court_slot_service
import app.services.session_service as session_service
import app.services.venue_service as venue_service


def calculate(
    session: SessionWithRoster,
    shuttle_batches: dict[UUID, ShuttleBatch],
    court_cost_per_hour: float,
    court_slots: list[CourtSlot],
    booker_names: dict[UUID, str],
    internal_player_ids: set[UUID] | None = None,
) -> PnLResult:
    """Pure function — no DB calls. Returns PnL breakdown."""
    if internal_player_ids is None:
        internal_player_ids = set()

    # Fees from external, non-waitlisted, verified_paid roster entries
    fee_paying_entries = [
        e
        for e in session.roster
        if not e.is_waitlisted
        and e.payment_status == "verified_paid"
        and (e.player_id is None or e.player_id not in internal_player_ids)
    ]
    total_fees_collected = len(fee_paying_entries) * session.pub_fee

    # Court cost from slot durations (each slot: cost_per_hour × hours)
    slot_costs: dict[UUID, float] = defaultdict(float)
    for slot in court_slots:
        start_dt = datetime.combine(session.date, slot.from_time, tzinfo=timezone.utc)
        end_dt = datetime.combine(session.date, slot.to_time, tzinfo=timezone.utc)
        hours = (end_dt - start_dt).total_seconds() / 3600
        cost = court_cost_per_hour * hours
        slot_costs[slot.booker_player_id] += cost

    court_cost = sum(slot_costs.values())

    booker_breakdown = [
        BookerReimbursement(
            player_id=player_id,
            player_name=booker_names.get(player_id, "Unknown"),
            amount=amount,
        )
        for player_id, amount in slot_costs.items()
    ]

    # Shuttle cost
    shuttle_cost = sum(
        usage.count_used * shuttle_batches[usage.batch_id].cost_per_shuttle
        for usage in session.shuttle_usage
        if usage.batch_id in shuttle_batches
    )

    net = total_fees_collected - court_cost - shuttle_cost

    return PnLResult(
        session_id=session.id,
        total_fees_collected=total_fees_collected,
        court_cost=court_cost,
        shuttle_cost=shuttle_cost,
        net=net,
        external_paid_count=len(fee_paying_entries),
        total_roster_count=len(session.roster),
        booker_breakdown=booker_breakdown,
    )


def get_session_pnl(session_id: UUID) -> PnLResult:
    """Fetch all needed data then calculate PnL."""
    session = session_service.get_by_id(session_id)
    venue = venue_service.get_by_id(session.venue_id)
    client = get_service_client()

    # Shuttle batches referenced in this session
    batch_ids = {u.batch_id for u in session.shuttle_usage}
    shuttle_batches: dict[UUID, ShuttleBatch] = {}
    if batch_ids:
        result = (
            client.table("shuttle_batches")
            .select("*")
            .in_("id", [str(bid) for bid in batch_ids])
            .execute()
        )
        shuttle_batches = {
            batch.id: batch
            for batch in (ShuttleBatch(**row) for row in result.data)
        }

    # Court slots for this session
    slots = court_slot_service.get_by_session(session_id)

    # Resolve booker names in one query
    booker_player_ids = list({str(s.booker_player_id) for s in slots})
    booker_names: dict[UUID, str] = {}
    if booker_player_ids:
        name_result = (
            client.table("players")
            .select("id, name")
            .in_("id", booker_player_ids)
            .execute()
        )
        booker_names = {UUID(row["id"]): row["name"] for row in name_result.data}

    # Internal player IDs excluded from fee income
    internal_result = (
        client.table("players").select("id").eq("is_internal", True).execute()
    )
    internal_player_ids = {UUID(row["id"]) for row in internal_result.data}

    return calculate(
        session=session,
        shuttle_batches=shuttle_batches,
        court_cost_per_hour=venue.court_cost_per_hour,
        court_slots=slots,
        booker_names=booker_names,
        internal_player_ids=internal_player_ids,
    )
