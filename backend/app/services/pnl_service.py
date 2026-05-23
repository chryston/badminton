from datetime import datetime, timezone
from uuid import UUID
from app.db.client import get_service_client
from app.models.session import SessionWithRoster
from app.models.shuttle import ShuttleBatch
from app.models.roster import PnLResult
import app.services.session_service as session_service
import app.services.venue_service as venue_service
import app.services.shuttle_service as shuttle_service


def calculate(
    session: SessionWithRoster,
    shuttle_batches: dict[UUID, ShuttleBatch],
    court_cost_per_hour: float,
    internal_player_ids: set[UUID] | None = None,
) -> PnLResult:
    """Pure function — no DB calls. Returns PnL breakdown."""
    if internal_player_ids is None:
        internal_player_ids = set()

    # Fees collected from external, non-waitlisted, verified_paid roster entries
    fee_paying_entries = [
        e
        for e in session.roster
        if not e.is_waitlisted
        and e.payment_status == "verified_paid"
        and (e.player_id is None or e.player_id not in internal_player_ids)
    ]
    total_fees_collected = len(fee_paying_entries) * session.pub_fee

    # Court cost: cost_per_hour × hours × num_courts
    start_dt = datetime.combine(session.date, session.start_time, tzinfo=timezone.utc)
    end_dt = datetime.combine(session.date, session.end_time, tzinfo=timezone.utc)
    hours = (end_dt - start_dt).total_seconds() / 3600
    court_cost = court_cost_per_hour * hours * session.num_courts

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
        verified_paid_count=len(fee_paying_entries),
        total_roster_count=len(session.roster),
    )


def get_session_pnl(session_id: UUID) -> PnLResult:
    """Fetch all needed data then calculate PnL."""
    session = session_service.get_by_id(session_id)
    venue = venue_service.get_by_id(session.venue_id)

    # Build shuttle_batches lookup for batches referenced in session
    batch_ids = {u.batch_id for u in session.shuttle_usage}
    shuttle_batches: dict[UUID, ShuttleBatch] = {}
    if batch_ids:
        client = get_service_client()
        result = (
            client.table("shuttle_batches")
            .select("*")
            .in_("id", [str(bid) for bid in batch_ids])
            .execute()
        )
        shuttle_batches = {ShuttleBatch(**row).id: ShuttleBatch(**row) for row in result.data}

    # Collect internal player ids for exclusion from fee calculation
    client = get_service_client()
    internal_result = (
        client.table("players").select("id").eq("is_internal", True).execute()
    )
    internal_player_ids = {
        UUID(row["id"]) for row in internal_result.data
    }

    return calculate(
        session=session,
        shuttle_batches=shuttle_batches,
        court_cost_per_hour=venue.court_cost_per_hour,
        internal_player_ids=internal_player_ids,
    )
