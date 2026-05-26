# Session Schema V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the 422 session-creation error and upgrade the session schema to support skill ranges, duration-based end_time (GENERATED column), court slots for P&L cost attribution, and atomic DB creation via RPC.

**Architecture:** DB migration 005 adds new columns/table/RPC; backend models, services and routers are updated in dependency order (models → services → routers); frontend types and pages are updated last; all existing tests are updated to use the new schema.

**Tech Stack:** PostgreSQL (Supabase), FastAPI + Pydantic v2, React + TypeScript + Tailwind, python-telegram-bot

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `supabase/migrations/005_session_schema_v2.sql` | All DB changes: new columns, GENERATED end_time, court_slots table, RPC, skill CHECK update |
| Modify | `backend/app/models/session.py` | New SessionCreate (court_slots, duration_hours, min/max skill), updated SessionUpdate, Session |
| Create | `backend/app/models/court_slot.py` | CourtSlot and CourtSlotCreate Pydantic models |
| Modify | `backend/app/models/roster.py` | Add BookerReimbursement; extend PnLResult with booker_breakdown |
| Create | `backend/app/services/court_slot_service.py` | get_by_session, add_slot, remove_slot |
| Modify | `backend/app/services/session_service.py` | create() uses RPC; remove manual end_time calc; max_pax default |
| Modify | `backend/app/services/pnl_service.py` | calculate() takes court_slots + booker_names; get_session_pnl fetches them |
| Create | `backend/app/routers/court_slots.py` | GET/POST/DELETE /sessions/{id}/court-slots |
| Modify | `backend/app/main.py` | Wire court_slots router |
| Modify | `backend/app/bot/message_formatter.py` | skill_level → min/max display |
| Modify | `frontend/src/types/index.ts` | Updated Session, SkillLevel, PnLResult; new CourtSlot, BookerReimbursement |
| Modify | `frontend/src/pages/NewSession.tsx` | Full rewrite with new form fields + court slots table |
| Modify | `frontend/src/pages/Sessions.tsx` | Show min–max skill range on session cards |
| Modify | `frontend/src/pages/SessionDetail.tsx` | Show skill range; court slots section; booker_breakdown in P&L |
| Modify | `frontend/src/pages/PnL.tsx` | Use total_fees_collected (fix field name); show booker_breakdown |
| Create | `backend/tests/test_court_slot_service.py` | get_by_session, add_slot, remove_slot behaviour |
| Modify | `backend/tests/test_pnl_service.py` | Use new Session model; pass court_slots + booker_names to calculate() |
| Modify | `backend/tests/test_message_formatter.py` | Use new Session model; assert min–max skill display |
| Modify | `backend/tests/test_session_flow_e2e.py` | New SessionCreate payload; updated mock responses; court_slots in P&L |

---

## Task 1: DB Migration 005

**Files:**
- Create: `supabase/migrations/005_session_schema_v2.sql`

- [ ] **Step 1: Create the migration file**

```sql
-- supabase/migrations/005_session_schema_v2.sql
-- Session Schema V2: skill range, duration, GENERATED end_time, court_slots, RPC
-- Fully idempotent — safe to re-run.

-- ── Step 1: Add new nullable columns to sessions ──────────────────────────────
ALTER TABLE sessions
    ADD COLUMN IF NOT EXISTS min_skill_level text,
    ADD COLUMN IF NOT EXISTS max_skill_level text,
    ADD COLUMN IF NOT EXISTS duration_hours   numeric;

-- ── Step 2: Backfill duration_hours for existing rows ─────────────────────────
UPDATE sessions SET duration_hours = 2.0 WHERE duration_hours IS NULL;

-- ── Step 3: Data-migrate skill_level (idempotency-guarded) ───────────────────
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'sessions' AND column_name = 'skill_level'
    ) THEN
        UPDATE sessions
        SET
            min_skill_level = CASE
                WHEN skill_level = 'HB - LI'                        THEN 'HB'
                WHEN skill_level IN ('LB','MB','HB','LI','MI','HI','A') THEN skill_level
                ELSE 'LI'
            END,
            max_skill_level = CASE
                WHEN skill_level = 'HB - LI'                        THEN 'LI'
                WHEN skill_level IN ('LB','MB','HB','LI','MI','HI','A') THEN skill_level
                ELSE 'MI'
            END
        WHERE min_skill_level IS NULL;
    END IF;
END $$;

-- ── Step 4: Apply NOT NULL constraints ────────────────────────────────────────
ALTER TABLE sessions
    ALTER COLUMN min_skill_level SET NOT NULL,
    ALTER COLUMN max_skill_level SET NOT NULL,
    ALTER COLUMN duration_hours   SET NOT NULL;

-- ── Step 5: Add CHECK constraints on skill level ──────────────────────────────
ALTER TABLE sessions
    DROP CONSTRAINT IF EXISTS sessions_min_skill_level_check,
    ADD  CONSTRAINT sessions_min_skill_level_check
        CHECK (min_skill_level IN ('LB','MB','HB','LI','MI','HI','A')),
    DROP CONSTRAINT IF EXISTS sessions_max_skill_level_check,
    ADD  CONSTRAINT sessions_max_skill_level_check
        CHECK (max_skill_level IN ('LB','MB','HB','LI','MI','HI','A'));

-- ── Step 6: Drop old skill_level column (if still present) ───────────────────
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'sessions' AND column_name = 'skill_level'
    ) THEN
        ALTER TABLE sessions DROP COLUMN skill_level;
    END IF;
END $$;

-- ── Step 7: Convert end_time to a GENERATED ALWAYS AS column ─────────────────
-- Drop the existing plain column and re-add as computed.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'sessions'
          AND column_name = 'end_time'
          AND is_generated = 'NEVER'
    ) THEN
        ALTER TABLE sessions DROP COLUMN end_time;
        ALTER TABLE sessions
            ADD COLUMN end_time time
                GENERATED ALWAYS AS (
                    (start_time + (duration_hours * interval '1 hour'))::time
                ) STORED;
    END IF;
END $$;

-- ── Step 8: Expand players.skill_level CHECK to 7 values ─────────────────────
ALTER TABLE players
    DROP CONSTRAINT IF EXISTS players_skill_level_check,
    ADD  CONSTRAINT players_skill_level_check
        CHECK (skill_level IN ('LB','MB','HB','LI','MI','HI','A'));

-- ── Step 9: Create court_slots table ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS court_slots (
    id                uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id        uuid        NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    court_label       text        NOT NULL,
    from_time         time        NOT NULL,
    to_time           time        NOT NULL,
    booker_player_id  uuid        NOT NULL REFERENCES players(id) ON DELETE RESTRICT,
    created_at        timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT court_slot_time_order CHECK (to_time > from_time)
);

CREATE INDEX IF NOT EXISTS idx_court_slots_session_id ON court_slots(session_id);

-- ── Step 10: RLS for court_slots ─────────────────────────────────────────────
ALTER TABLE court_slots ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'court_slots'
          AND policyname = 'Court slots readable by authenticated users'
    ) THEN
        CREATE POLICY "Court slots readable by authenticated users"
            ON court_slots FOR SELECT TO authenticated USING (true);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'court_slots'
          AND policyname = 'Court slots managed by service role'
    ) THEN
        CREATE POLICY "Court slots managed by service role"
            ON court_slots FOR ALL TO service_role USING (true);
    END IF;
END $$;

-- ── Step 11: RPC for atomic session + slots creation ─────────────────────────
CREATE OR REPLACE FUNCTION create_session_with_slots(
    session_data jsonb,
    slots_data   jsonb
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    new_session_id uuid;
    slot           jsonb;
    result_row     jsonb;
BEGIN
    INSERT INTO sessions (
        venue_id, date, start_time, duration_hours,
        courts_booked, num_courts, min_skill_level, max_skill_level,
        pub_fee, max_pax, status, paynow_player_id
    ) VALUES (
        (session_data->>'venue_id')::uuid,
        (session_data->>'date')::date,
        (session_data->>'start_time')::time,
        (session_data->>'duration_hours')::numeric,
        session_data->>'courts_booked',
        (session_data->>'num_courts')::int,
        session_data->>'min_skill_level',
        session_data->>'max_skill_level',
        (session_data->>'pub_fee')::numeric,
        (session_data->>'max_pax')::int,
        'internal',
        NULLIF(session_data->>'paynow_player_id', '')::uuid
    )
    RETURNING id INTO new_session_id;

    FOR slot IN SELECT * FROM jsonb_array_elements(slots_data)
    LOOP
        INSERT INTO court_slots (session_id, court_label, from_time, to_time, booker_player_id)
        VALUES (
            new_session_id,
            slot->>'court_label',
            (slot->>'from_time')::time,
            (slot->>'to_time')::time,
            (slot->>'booker_player_id')::uuid
        );
    END LOOP;

    SELECT row_to_json(s)::jsonb INTO result_row
    FROM sessions s
    WHERE s.id = new_session_id;

    RETURN result_row;
END;
$$;
```

- [ ] **Step 2: Apply the migration to Supabase**

```bash
# If using Supabase CLI linked to your project:
supabase db push

# Or apply directly via psql (replace with your DB URL):
psql "$DATABASE_URL" -f supabase/migrations/005_session_schema_v2.sql
```

Expected: no errors. Verify with:
```bash
psql "$DATABASE_URL" -c "\d sessions" | grep -E "end_time|min_skill|max_skill|duration"
# Should show end_time as "generated"
psql "$DATABASE_URL" -c "\dt court_slots"
# Should show court_slots table
```

- [ ] **Step 3: Commit**

```bash
git add supabase/migrations/005_session_schema_v2.sql
git commit -m "db: add session schema v2 migration

- min/max skill_level replacing single skill_level
- duration_hours stored; end_time GENERATED ALWAYS AS
- court_slots table for P&L cost attribution
- RPC create_session_with_slots for atomic creation"
```

---

## Task 2: Backend Models

**Files:**
- Modify: `backend/app/models/session.py`
- Create: `backend/app/models/court_slot.py`
- Modify: `backend/app/models/roster.py`

- [ ] **Step 1: Create `backend/app/models/court_slot.py`**

```python
from datetime import datetime, time
from uuid import UUID
from pydantic import BaseModel


class CourtSlot(BaseModel):
    id: UUID
    session_id: UUID
    court_label: str
    from_time: time
    to_time: time
    booker_player_id: UUID
    created_at: datetime


class CourtSlotCreate(BaseModel):
    court_label: str
    from_time: time
    to_time: time
    booker_player_id: UUID
```

- [ ] **Step 2: Replace `backend/app/models/session.py`**

```python
from datetime import date, datetime, time
from typing import Annotated
from uuid import UUID
from pydantic import BaseModel, Field

from app.models.court_slot import CourtSlotCreate
from app.models.shuttle import ShuttleUsage

_SKILL_LEVELS = ('LB', 'MB', 'HB', 'LI', 'MI', 'HI', 'A')


class Session(BaseModel):
    id: UUID
    venue_id: UUID
    date: date
    start_time: time
    end_time: time           # GENERATED by DB — always consistent with start_time + duration_hours
    duration_hours: float
    courts_booked: str
    num_courts: int
    min_skill_level: str
    max_skill_level: str
    pub_fee: float
    max_pax: int
    status: str              # internal | published | completed
    telegram_message_id: int | None = None
    paynow_player_id: UUID | None = None
    created_at: datetime


class SessionCreate(BaseModel):
    venue_id: UUID
    date: date
    start_time: time
    duration_hours: float = 2.0
    courts_booked: str
    num_courts: int = 1
    min_skill_level: str = "LI"
    max_skill_level: str = "MI"
    pub_fee: float
    max_pax: Annotated[int, Field(gt=0)] | None = None  # None → service sets num_courts × 6
    paynow_player_id: UUID | None = None
    court_slots: Annotated[list[CourtSlotCreate], Field(min_length=1)]


class SessionUpdate(BaseModel):
    date: date | None = None
    start_time: time | None = None
    duration_hours: float | None = None  # updating this recomputes DB end_time automatically
    courts_booked: str | None = None
    num_courts: int | None = None
    min_skill_level: str | None = None
    max_skill_level: str | None = None
    pub_fee: float | None = None
    max_pax: Annotated[int, Field(gt=0)] | None = None
    paynow_player_id: UUID | None = None
    telegram_message_id: int | None = None


class SessionWithRoster(Session):
    roster: list["RosterEntry"] = []
    shuttle_usage: list[ShuttleUsage] = []
    active_count: int = 0
    waitlist_count: int = 0


# Forward reference resolved below
from app.models.roster import RosterEntry
SessionWithRoster.model_rebuild()
```

- [ ] **Step 3: Update `backend/app/models/roster.py` — add BookerReimbursement, extend PnLResult**

```python
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel


class RosterEntry(BaseModel):
    id: UUID
    session_id: UUID
    player_id: UUID | None = None
    guest_name: str | None = None
    player_type: str  # registered | guest
    payment_status: str  # unpaid | pending_verification | verified_paid
    is_waitlisted: bool = False
    position: int
    joined_at: datetime
    created_at: datetime

    @property
    def display_name(self) -> str:
        return self.guest_name or ""  # name resolved by service layer


class RosterEntryCreate(BaseModel):
    guest_name: str  # for manually adding external players


class BookerReimbursement(BaseModel):
    player_id: UUID
    player_name: str
    amount: float


class PnLResult(BaseModel):
    session_id: UUID
    total_fees_collected: float
    court_cost: float
    shuttle_cost: float
    net: float
    external_paid_count: int
    total_roster_count: int
    booker_breakdown: list[BookerReimbursement] = []
```

- [ ] **Step 4: Verify models load without errors**

```bash
cd backend
python -c "from app.models.session import Session, SessionCreate, SessionUpdate; from app.models.court_slot import CourtSlot, CourtSlotCreate; from app.models.roster import PnLResult, BookerReimbursement; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/
git commit -m "feat: update backend models for session schema v2

- SessionCreate: duration_hours, min/max skill, court_slots (min 1)
- SessionUpdate: all new fields included
- Session: end_time is GENERATED (read from DB, not set by service)
- New court_slot.py: CourtSlot + CourtSlotCreate
- roster.py: BookerReimbursement + PnLResult.booker_breakdown"
```

---

## Task 3: CourtSlot Service + Tests

**Files:**
- Create: `backend/app/services/court_slot_service.py`
- Create: `backend/tests/test_court_slot_service.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_court_slot_service.py
"""Unit tests for court_slot_service — behaviour, minimal mocking."""
from datetime import time, datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.models.court_slot import CourtSlotCreate
from app.services.court_slot_service import get_by_session, add_slot, remove_slot

_SESSION_ID = uuid4()
_SLOT_ID = uuid4()
_BOOKER_ID = uuid4()
_NOW = datetime.now(timezone.utc)

_SLOT_ROW = {
    "id": str(_SLOT_ID),
    "session_id": str(_SESSION_ID),
    "court_label": "Court 1",
    "from_time": "09:00:00",
    "to_time": "11:00:00",
    "booker_player_id": str(_BOOKER_ID),
    "created_at": _NOW.isoformat(),
}


def _make_mock_db():
    client = MagicMock()
    builder = MagicMock()
    for method in ("select", "insert", "update", "delete", "eq", "order", "in_"):
        getattr(builder, method).return_value = builder
    client.table.return_value = builder
    return client, builder


def test_get_by_session_returns_slots():
    """Returns CourtSlot objects for the given session."""
    client, builder = _make_mock_db()
    builder.execute.return_value = MagicMock(data=[_SLOT_ROW])

    with patch("app.db.client._service_client", client):
        slots = get_by_session(_SESSION_ID)

    assert len(slots) == 1
    assert slots[0].court_label == "Court 1"
    assert slots[0].from_time == time(9, 0)
    assert slots[0].booker_player_id == _BOOKER_ID


def test_get_by_session_empty():
    """Returns empty list when session has no slots."""
    client, builder = _make_mock_db()
    builder.execute.return_value = MagicMock(data=[])

    with patch("app.db.client._service_client", client):
        slots = get_by_session(_SESSION_ID)

    assert slots == []


def test_add_slot_inserts_and_returns():
    """Inserts a court slot and returns the persisted CourtSlot."""
    client, builder = _make_mock_db()
    builder.execute.return_value = MagicMock(data=[_SLOT_ROW])

    data = CourtSlotCreate(
        court_label="Court 1",
        from_time=time(9, 0),
        to_time=time(11, 0),
        booker_player_id=_BOOKER_ID,
    )

    with patch("app.db.client._service_client", client):
        slot = add_slot(_SESSION_ID, data)

    assert slot.court_label == "Court 1"
    assert slot.booker_player_id == _BOOKER_ID


def test_remove_slot_calls_delete():
    """Calls delete with the correct slot id."""
    client, builder = _make_mock_db()
    builder.execute.return_value = MagicMock(data=[])

    with patch("app.db.client._service_client", client):
        remove_slot(_SLOT_ID)

    builder.delete.assert_called_once()
    builder.eq.assert_called_with("id", str(_SLOT_ID))
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd backend
pytest tests/test_court_slot_service.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.services.court_slot_service'`

- [ ] **Step 3: Create `backend/app/services/court_slot_service.py`**

```python
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
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd backend
pytest tests/test_court_slot_service.py -v
```

Expected: 4 tests PASSED

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/court_slot_service.py backend/tests/test_court_slot_service.py
git commit -m "feat: add court_slot_service with tests"
```

---

## Task 4: Update Session Service

**Files:**
- Modify: `backend/app/services/session_service.py`

- [ ] **Step 1: Replace the `create()` function in `session_service.py`**

Replace the entire `create` function (keep all other functions unchanged):

```python
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

    internal_result = (
        client.table("players").select("*").eq("is_internal", True).order("name").execute()
    )

    if internal_result.data:
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
            for i, player in enumerate(internal_result.data, 1)
        ]
        client.table("roster_entries").insert(roster_rows).execute()

    return session
```

Also update the import at the top of the file — `SessionCreate` now comes from the same models file, no change needed, but make sure the import includes it:

```python
from app.models.session import Session, SessionCreate, SessionUpdate, SessionWithRoster
```

- [ ] **Step 2: Verify the service imports cleanly**

```bash
cd backend
python -c "from app.services.session_service import create, get_all, get_by_id, update, publish, complete; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/session_service.py
git commit -m "feat: session_service.create() uses atomic RPC

- Calls create_session_with_slots RPC (transactional)
- Removes manual end_time computation (DB GENERATED)
- max_pax defaults to num_courts × 6 in service"
```

---

## Task 5: Update PnL Service

**Files:**
- Modify: `backend/app/services/pnl_service.py`

- [ ] **Step 1: Replace `backend/app/services/pnl_service.py`**

```python
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
import app.services.shuttle_service as shuttle_service


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
```

- [ ] **Step 2: Verify import**

```bash
cd backend
python -c "from app.services.pnl_service import calculate, get_session_pnl; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/pnl_service.py
git commit -m "feat: pnl_service uses court_slots for cost attribution

- calculate() takes court_slots + booker_names (stays pure)
- court_cost derived from slot durations, not num_courts × hours
- booker_breakdown shows per-booker reimbursement
- get_session_pnl() pre-fetches slots + names before calling calculate()"
```

---

## Task 6: Court Slots Router + Wire into main.py

**Files:**
- Create: `backend/app/routers/court_slots.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create `backend/app/routers/court_slots.py`**

```python
from uuid import UUID

from fastapi import APIRouter, Depends

from app.dependencies import require_admin
from app.models.court_slot import CourtSlot, CourtSlotCreate
import app.services.court_slot_service as court_slot_service

router = APIRouter()


@router.get("/sessions/{session_id}/court-slots", response_model=list[CourtSlot])
def list_court_slots(session_id: UUID, _=Depends(require_admin)):
    return court_slot_service.get_by_session(session_id)


@router.post("/sessions/{session_id}/court-slots", response_model=CourtSlot, status_code=201)
def add_court_slot(session_id: UUID, data: CourtSlotCreate, _=Depends(require_admin)):
    return court_slot_service.add_slot(session_id, data)


@router.delete("/sessions/{session_id}/court-slots/{slot_id}", status_code=204)
def remove_court_slot(session_id: UUID, slot_id: UUID, _=Depends(require_admin)):
    court_slot_service.remove_slot(slot_id)
```

- [ ] **Step 2: Wire court_slots router in `backend/app/main.py`**

Add the import and router line. Locate these lines in main.py:

```python
from app.routers import sessions, roster, players, inventory, pnl, venues
```

Replace with:

```python
from app.routers import sessions, roster, players, inventory, pnl, venues, court_slots
```

Then add after the existing `app.include_router(venues.router, ...)` line:

```python
app.include_router(court_slots.router, prefix="/api/v1", tags=["court-slots"])
```

- [ ] **Step 3: Verify FastAPI starts without errors**

```bash
cd backend
python -c "from app.main import app; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/app/routers/court_slots.py backend/app/main.py
git commit -m "feat: court_slots router (GET/POST/DELETE) wired into main.py"
```

---

## Task 7: Update Bot Message Formatter

**Files:**
- Modify: `backend/app/bot/message_formatter.py`

- [ ] **Step 1: Update the skill_level line in `format_session_announcement`**

Find this line in `format_session_announcement`:

```python
        f"🎯 Level: {session.skill_level}",
```

Replace with:

```python
        _skill_range_label(session.min_skill_level, session.max_skill_level),
```

- [ ] **Step 2: Add the `_skill_range_label` helper function** (add near the bottom with other private helpers):

```python
def _skill_range_label(min_level: str, max_level: str) -> str:
    if min_level == max_level:
        return f"🎯 Level: {min_level}"
    return f"🎯 Level: {min_level} – {max_level}"
```

- [ ] **Step 3: Verify the module imports cleanly**

```bash
cd backend
python -c "from app.bot.message_formatter import format_session_announcement; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/app/bot/message_formatter.py
git commit -m "feat: message_formatter uses min/max skill level range"
```

---

## Task 8: Update All Tests

**Files:**
- Modify: `backend/tests/test_pnl_service.py`
- Modify: `backend/tests/test_message_formatter.py`
- Modify: `backend/tests/test_session_flow_e2e.py`

- [ ] **Step 1: Replace `backend/tests/test_pnl_service.py`**

```python
"""Unit tests for pnl_service.calculate() — pure function, no mocks needed."""
from collections import defaultdict
from datetime import date, time, datetime, timezone
from uuid import UUID, uuid4

import pytest

from app.models.court_slot import CourtSlot
from app.models.roster import RosterEntry
from app.models.session import SessionWithRoster
from app.models.shuttle import ShuttleBatch, ShuttleUsage
from app.services.pnl_service import calculate

_SESSION_ID = uuid4()
_VENUE_ID = uuid4()
_BATCH_ID = uuid4()
_BOOKER_ID = uuid4()
_NOW = datetime.now(timezone.utc)


def _session(roster=None, shuttle_usage=None, pub_fee=10.0) -> SessionWithRoster:
    r = roster or []
    su = shuttle_usage or []
    return SessionWithRoster(
        id=_SESSION_ID,
        venue_id=_VENUE_ID,
        date=date(2025, 6, 15),
        start_time=time(9, 0),
        end_time=time(11, 0),
        duration_hours=2.0,
        courts_booked="Court 1",
        num_courts=1,
        min_skill_level="HB",
        max_skill_level="LI",
        pub_fee=pub_fee,
        max_pax=12,
        status="completed",
        created_at=_NOW,
        roster=r,
        shuttle_usage=su,
        active_count=sum(1 for e in r if not e.is_waitlisted),
        waitlist_count=sum(1 for e in r if e.is_waitlisted),
    )


def _entry(
    payment_status="verified_paid",
    is_waitlisted=False,
    player_id=None,
    position=1,
) -> RosterEntry:
    return RosterEntry(
        id=uuid4(),
        session_id=_SESSION_ID,
        player_id=player_id,
        player_type="registered" if player_id else "guest",
        payment_status=payment_status,
        is_waitlisted=is_waitlisted,
        position=position,
        joined_at=_NOW,
        created_at=_NOW,
    )


def _court_slot(from_hour: int = 9, to_hour: int = 11) -> CourtSlot:
    """One slot covering from_hour to to_hour on the session date."""
    return CourtSlot(
        id=uuid4(),
        session_id=_SESSION_ID,
        court_label="Court 1",
        from_time=time(from_hour, 0),
        to_time=time(to_hour, 0),
        booker_player_id=_BOOKER_ID,
        created_at=_NOW,
    )


def _calc(session, slots=None, **kwargs):
    """Helper: call calculate() with sensible defaults."""
    return calculate(
        session,
        shuttle_batches=kwargs.get("shuttle_batches", {}),
        court_cost_per_hour=kwargs.get("court_cost_per_hour", 15.0),
        court_slots=slots if slots is not None else [_court_slot()],
        booker_names=kwargs.get("booker_names", {_BOOKER_ID: "Belle"}),
        internal_player_ids=kwargs.get("internal_player_ids", None),
    )


def test_calculate_basic_profit():
    """5 paying external players × $10 = $50 income, $30 court cost = $20 profit."""
    roster = [_entry() for _ in range(5)]
    result = _calc(_session(roster=roster))
    assert result.net == 20.0


def test_calculate_income_calculation():
    """total_fees_collected and external_paid_count from verified_paid active entries."""
    roster = [_entry() for _ in range(5)]
    result = _calc(_session(roster=roster))
    assert result.total_fees_collected == 50.0
    assert result.external_paid_count == 5


def test_calculate_cost_breakdown():
    """court_cost = slot duration × rate; no shuttles = zero shuttle_cost."""
    roster = [_entry() for _ in range(5)]
    result = _calc(_session(roster=roster))
    assert result.court_cost == 30.0   # 2h × $15
    assert result.shuttle_cost == 0.0


def test_calculate_excludes_internal_players():
    """Internal players do not contribute to fee income."""
    internal_id_1 = uuid4()
    internal_id_2 = uuid4()
    roster = [
        _entry(player_id=uuid4()),
        _entry(player_id=uuid4()),
        _entry(player_id=uuid4()),
        _entry(player_id=internal_id_1),
        _entry(player_id=internal_id_2),
    ]
    result = _calc(
        _session(roster=roster),
        internal_player_ids={internal_id_1, internal_id_2},
    )
    assert result.total_fees_collected == 30.0
    assert result.external_paid_count == 3
    assert result.total_roster_count == 5


def test_calculate_excludes_waitlisted():
    """Waitlisted players do not contribute to income."""
    roster = [
        _entry(position=1),
        _entry(position=2),
        _entry(payment_status="verified_paid", is_waitlisted=True, position=3),
    ]
    result = _calc(_session(roster=roster))
    assert result.total_fees_collected == 20.0
    assert result.external_paid_count == 2


def test_calculate_deficit():
    """Net is negative when costs exceed income."""
    roster = [_entry()]
    result = _calc(_session(roster=roster))
    assert result.total_fees_collected == 10.0
    assert result.net == -20.0


def test_calculate_zero_shuttles():
    """Zero shuttle usage produces zero shuttle_cost."""
    result = _calc(_session())
    assert result.shuttle_cost == 0.0
    assert result.net == -30.0  # 0 income - $30 court


def test_calculate_shuttle_cost():
    """Shuttle cost = count_used × cost_per_shuttle per batch."""
    batch = ShuttleBatch(
        id=_BATCH_ID,
        batch_name="RSL Sonic 6",
        brand="RSL",
        cost_per_tube=20.0,
        shuttles_per_tube=12,
        cost_per_shuttle=20.0 / 12,
        remaining_count=50,
        created_at=_NOW,
    )
    usage = ShuttleUsage(
        id=uuid4(),
        session_id=_SESSION_ID,
        batch_id=_BATCH_ID,
        count_used=6,
        created_at=_NOW,
    )
    roster = [_entry() for _ in range(5)]
    result = _calc(
        _session(roster=roster, shuttle_usage=[usage]),
        shuttle_batches={_BATCH_ID: batch},
    )
    expected_shuttle = 6 * (20.0 / 12)
    assert abs(result.shuttle_cost - expected_shuttle) < 0.001
    assert result.net == pytest.approx(50.0 - 30.0 - expected_shuttle)


def test_calculate_booker_breakdown():
    """booker_breakdown shows each booker's slot cost."""
    booker_a = uuid4()
    booker_b = uuid4()
    slots = [
        CourtSlot(
            id=uuid4(), session_id=_SESSION_ID, court_label="Court 1",
            from_time=time(9, 0), to_time=time(11, 0),
            booker_player_id=booker_a, created_at=_NOW,
        ),
        CourtSlot(
            id=uuid4(), session_id=_SESSION_ID, court_label="Court 2",
            from_time=time(9, 0), to_time=time(10, 0),
            booker_player_id=booker_b, created_at=_NOW,
        ),
    ]
    result = calculate(
        _session(),
        shuttle_batches={},
        court_cost_per_hour=15.0,
        court_slots=slots,
        booker_names={booker_a: "Alice", booker_b: "Bob"},
    )
    breakdown = {b.player_name: b.amount for b in result.booker_breakdown}
    assert breakdown["Alice"] == 30.0   # 2h × $15
    assert breakdown["Bob"] == 15.0     # 1h × $15
    assert result.court_cost == 45.0
```

- [ ] **Step 2: Replace `backend/tests/test_message_formatter.py`**

```python
"""Unit tests for bot/message_formatter.py — pure functions, no mocks needed."""
from datetime import date, time, datetime, timezone
from uuid import UUID, uuid4

from app.bot.message_formatter import format_session_announcement, build_join_button
from app.models.roster import RosterEntry
from app.models.session import Session

_NOW = datetime.now(timezone.utc)
_SESSION_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_VENUE_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


def _session(max_pax=12, min_skill="HB", max_skill="LI") -> Session:
    return Session(
        id=_SESSION_ID,
        venue_id=_VENUE_ID,
        date=date(2025, 6, 15),
        start_time=time(9, 0),
        end_time=time(11, 0),
        duration_hours=2.0,
        courts_booked="Court 1",
        num_courts=1,
        min_skill_level=min_skill,
        max_skill_level=max_skill,
        pub_fee=10.0,
        max_pax=max_pax,
        status="published",
        created_at=_NOW,
    )


def _entry(player_id=None, guest_name=None, payment_status="unpaid", is_waitlisted=False, position=1) -> RosterEntry:
    return RosterEntry(
        id=uuid4(),
        session_id=_SESSION_ID,
        player_id=player_id,
        guest_name=guest_name,
        player_type="registered" if player_id else "guest",
        payment_status=payment_status,
        is_waitlisted=is_waitlisted,
        position=position,
        joined_at=_NOW,
        created_at=_NOW,
    )


def test_format_announcement_shows_numbered_players():
    """Active players appear as '1. Alice', '2. Bob'."""
    alice_id = uuid4()
    bob_id = uuid4()
    roster = [
        _entry(player_id=alice_id, position=1),
        _entry(player_id=bob_id, position=2),
    ]
    player_names = {alice_id: "Alice", bob_id: "Bob"}
    text = format_session_announcement(
        _session(), roster, player_names,
        venue_name="Test Hall", paynow_name="Admin", paynow_phone="91234567",
    )
    assert "1. Alice" in text
    assert "2. Bob" in text


def test_format_announcement_paid_label():
    """verified_paid entry shows '(paid)' suffix."""
    player_id = uuid4()
    roster = [_entry(player_id=player_id, payment_status="verified_paid", position=1)]
    player_names = {player_id: "Alice"}
    text = format_session_announcement(
        _session(), roster, player_names,
        venue_name="Test Hall", paynow_name="Admin", paynow_phone="91234567",
    )
    assert "1. Alice (paid)" in text


def test_format_announcement_hides_waitlist_when_empty():
    """Waitlist section absent when no waitlisted entries."""
    player_id = uuid4()
    roster = [_entry(player_id=player_id, position=1)]
    player_names = {player_id: "Alice"}
    text = format_session_announcement(
        _session(), roster, player_names,
        venue_name="Test Hall", paynow_name="Admin", paynow_phone="91234567",
    )
    assert "Waitlist:" not in text


def test_format_announcement_shows_waitlist_when_present():
    """Waitlist section present with 'W1. Charlie' format."""
    alice_id = uuid4()
    charlie_id = uuid4()
    roster = [
        _entry(player_id=alice_id, is_waitlisted=False, position=1),
        _entry(player_id=charlie_id, is_waitlisted=True, position=2),
    ]
    player_names = {alice_id: "Alice", charlie_id: "Charlie"}
    text = format_session_announcement(
        _session(), roster, player_names,
        venue_name="Test Hall", paynow_name="Admin", paynow_phone="91234567",
    )
    assert "Waitlist:" in text
    assert "W1. Charlie" in text


def test_format_announcement_shows_full_count():
    """'Players (3/12)' shows active count and max_pax."""
    roster = [_entry(guest_name=f"Player {i}", position=i) for i in range(1, 4)]
    text = format_session_announcement(
        _session(max_pax=12), roster, {},
        venue_name="Test Hall", paynow_name="Admin", paynow_phone="91234567",
    )
    assert "Players (3/12):" in text


def test_format_announcement_skill_range():
    """Different min/max renders as 'HB – LI'."""
    text = format_session_announcement(
        _session(min_skill="HB", max_skill="LI"), [], {},
        venue_name="Test Hall", paynow_name="Admin", paynow_phone="91234567",
    )
    assert "🎯 Level: HB – LI" in text


def test_format_announcement_single_skill():
    """Same min/max renders as single level without dash."""
    text = format_session_announcement(
        _session(min_skill="LI", max_skill="LI"), [], {},
        venue_name="Test Hall", paynow_name="Admin", paynow_phone="91234567",
    )
    assert "🎯 Level: LI" in text
    assert "–" not in text


def test_join_button_callback_data():
    """Join button callback_data is 'join:{session_id}'."""
    markup = build_join_button("test-session-123")
    button = markup.inline_keyboard[0][0]
    assert button.callback_data == "join:test-session-123"
```

- [ ] **Step 3: Replace `backend/tests/test_session_flow_e2e.py`**

```python
"""
E2E test: Complete session lifecycle — updated for schema v2.

Workflow:
  1. Admin creates a session (with court_slots, duration_hours, min/max skill)
  2. Session is published (bot mocked)
  3. Guest player added to roster
  4. Admin verifies payment
  5. Admin completes session (no shuttles)
  6. P&L fetched and verified

Mocking:
  - app.db.client._service_client: sequential mock consuming responses in call order
  - bot_runner action methods: AsyncMock to prevent background tasks consuming DB mock responses
  - require_admin: overridden to bypass JWT check
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

_SESSION_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
_VENUE_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
_ENTRY_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
_BOOKER_ID = "dddddddd-dddd-dddd-dddd-dddddddddddd"
_COURT_SLOT_ID = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
_TS = "2025-01-01T10:00:00+00:00"

_SESSION_INTERNAL = {
    "id": _SESSION_ID,
    "venue_id": _VENUE_ID,
    "date": "2025-06-15",
    "start_time": "09:00:00",
    "end_time": "11:00:00",      # GENERATED by DB
    "duration_hours": 2.0,
    "courts_booked": "Court 1",
    "num_courts": 1,
    "min_skill_level": "HB",
    "max_skill_level": "LI",
    "pub_fee": 10.0,
    "max_pax": 12,
    "status": "internal",
    "telegram_message_id": None,
    "paynow_player_id": None,
    "created_at": _TS,
}

_SESSION_PUBLISHED = {**_SESSION_INTERNAL, "status": "published"}
_SESSION_COMPLETED = {**_SESSION_INTERNAL, "status": "completed"}

_ENTRY_UNPAID = {
    "id": _ENTRY_ID,
    "session_id": _SESSION_ID,
    "player_id": None,
    "guest_name": "Alice",
    "player_type": "guest",
    "payment_status": "unpaid",
    "is_waitlisted": False,
    "position": 1,
    "joined_at": _TS,
    "created_at": _TS,
}
_ENTRY_PAID = {**_ENTRY_UNPAID, "payment_status": "verified_paid"}

_VENUE_ROW = {
    "id": _VENUE_ID,
    "name": "Test Hall",
    "court_cost_per_hour": 15.0,
    "default_pub_fee": 10.0,
    "created_at": _TS,
}

_COURT_SLOT_ROW = {
    "id": _COURT_SLOT_ID,
    "session_id": _SESSION_ID,
    "court_label": "Court 1",
    "from_time": "09:00:00",
    "to_time": "11:00:00",
    "booker_player_id": _BOOKER_ID,
    "created_at": _TS,
}


def _session_with_roster():
    """Returns a fresh dict — pop() in get_by_id() mutates it, so never reuse."""
    return {
        **_SESSION_COMPLETED,
        "roster_entries": [dict(_ENTRY_PAID)],
        "shuttle_usage": [],
    }


def _make_mock_db():
    client = MagicMock()
    builder = MagicMock()
    for method in ("select", "insert", "update", "delete", "eq", "order", "limit", "maybe_single", "in_"):
        getattr(builder, method).return_value = builder
    client.table.return_value = builder
    client.rpc.return_value = builder   # RPC calls also chain to builder
    return client, builder


def test_complete_session_lifecycle():
    """Full E2E: create → publish → join (guest) → verify payment → complete → P&L."""
    from app.dependencies import require_admin
    from app.main import app

    mock_client, mock_builder = _make_mock_db()

    # Responses consumed in exact execute() call order across all service calls.
    mock_builder.execute.side_effect = [
        # ── create session (via RPC) ──────────────────────────────────────────
        MagicMock(data=_SESSION_INTERNAL),          # rpc.execute() → new session row
        MagicMock(data=[]),                          # players(is_internal) → no auto-roster
        # ── publish ──────────────────────────────────────────────────────────
        MagicMock(data=[{"status": "internal"}]),   # sessions.select("status")
        MagicMock(data=[_SESSION_PUBLISHED]),        # sessions.update(published)
        # ── add guest ────────────────────────────────────────────────────────
        MagicMock(data=[{"max_pax": 12}]),           # sessions.select("max_pax")
        MagicMock(data=[]),                          # roster_entries active count → 0
        MagicMock(data=[]),                          # roster_entries max position → none
        MagicMock(data=[_ENTRY_UNPAID]),             # roster_entries.insert
        # ── verify payment ───────────────────────────────────────────────────
        MagicMock(data=[_ENTRY_PAID]),               # roster_entries.update(verified_paid)
        # ── complete session ─────────────────────────────────────────────────
        MagicMock(data=[{"status": "published"}]),  # sessions.select("status")
        MagicMock(data=[_SESSION_COMPLETED]),        # sessions.update(completed)
        MagicMock(data=[_session_with_roster()]),    # get_by_id (nested select)
        # ── P&L ──────────────────────────────────────────────────────────────
        MagicMock(data=[_session_with_roster()]),    # get_by_id
        MagicMock(data=[_VENUE_ROW]),                # venues.select
        MagicMock(data=[_COURT_SLOT_ROW]),           # court_slots.select
        MagicMock(data=[{"id": _BOOKER_ID, "name": "Belle"}]),  # booker names
        MagicMock(data=[]),                          # players(is_internal) for exclusion
    ]

    app.dependency_overrides[require_admin] = lambda: None

    try:
        with (
            patch("app.db.client._service_client", mock_client),
            patch("app.bot.runner.bot_runner.build"),
            patch("app.bot.runner.bot_runner.start_polling", new_callable=AsyncMock),
            patch("app.bot.runner.bot_runner.post_session_announcement", new_callable=AsyncMock),
            patch("app.bot.runner.bot_runner.edit_session_message", new_callable=AsyncMock),
            patch("app.bot.runner.bot_runner.update_payment_in_message", new_callable=AsyncMock),
        ):
            with TestClient(app) as client:
                headers = {"Authorization": "Bearer test-token"}

                # 1. Create session
                resp = client.post(
                    "/api/v1/sessions",
                    json={
                        "venue_id": _VENUE_ID,
                        "date": "2025-06-15",
                        "start_time": "09:00:00",
                        "duration_hours": 2.0,
                        "courts_booked": "Court 1",
                        "num_courts": 1,
                        "min_skill_level": "HB",
                        "max_skill_level": "LI",
                        "pub_fee": 10.0,
                        "max_pax": 12,
                        "court_slots": [
                            {
                                "court_label": "Court 1",
                                "from_time": "09:00:00",
                                "to_time": "11:00:00",
                                "booker_player_id": _BOOKER_ID,
                            }
                        ],
                    },
                    headers=headers,
                )
                assert resp.status_code == 201, resp.text
                assert resp.json()["status"] == "internal"

                # 2. Publish session
                resp = client.post(f"/api/v1/sessions/{_SESSION_ID}/publish", headers=headers)
                assert resp.status_code == 200, resp.text
                assert resp.json()["status"] == "published"

                # 3. Add a guest player
                resp = client.post(
                    f"/api/v1/sessions/{_SESSION_ID}/roster/guest",
                    json={"guest_name": "Alice"},
                    headers=headers,
                )
                assert resp.status_code == 201, resp.text
                assert resp.json()["guest_name"] == "Alice"
                assert resp.json()["payment_status"] == "unpaid"

                # 4. Verify payment
                resp = client.post(
                    f"/api/v1/sessions/{_SESSION_ID}/roster/{_ENTRY_ID}/verify",
                    headers=headers,
                )
                assert resp.status_code == 200, resp.text
                assert resp.json()["payment_status"] == "verified_paid"

                # 5. Complete session (no shuttles)
                resp = client.post(
                    f"/api/v1/sessions/{_SESSION_ID}/complete",
                    json=[],
                    headers=headers,
                )
                assert resp.status_code == 200, resp.text
                assert resp.json()["status"] == "completed"

                # 6. Fetch P&L
                resp = client.get(f"/api/v1/sessions/{_SESSION_ID}/pnl", headers=headers)
                assert resp.status_code == 200, resp.text
                pnl = resp.json()

                # 1 external verified_paid × $10 = $10 income
                # Court slot 09:00–11:00 × $15/hr = $30 court cost
                # net = $10 - $30 = -$20
                assert pnl["total_fees_collected"] == 10.0
                assert pnl["court_cost"] == 30.0
                assert pnl["shuttle_cost"] == 0.0
                assert pnl["net"] == -20.0
                assert pnl["external_paid_count"] == 1
                assert len(pnl["booker_breakdown"]) == 1
                assert pnl["booker_breakdown"][0]["amount"] == 30.0
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 4: Run all tests — verify they pass**

```bash
cd backend
pytest tests/ -v
```

Expected: All tests PASS (15 existing + 4 new court_slot + 2 new formatter = 21 total)

- [ ] **Step 5: Commit**

```bash
git add backend/tests/
git commit -m "test: update all tests for session schema v2

- test_pnl_service: new Session fixture, court_slots param, booker_breakdown test
- test_message_formatter: new Session fixture, skill range assertions
- test_session_flow_e2e: new SessionCreate payload, RPC mock, court_slots in P&L"
```

---

## Task 9: Frontend Types

**Files:**
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Replace `frontend/src/types/index.ts`**

```typescript
export type SkillLevel = 'LB' | 'MB' | 'HB' | 'LI' | 'MI' | 'HI' | 'A';
export type PaymentStatus = 'unpaid' | 'pending_verification' | 'verified_paid';
export type SessionStatus = 'internal' | 'published' | 'completed';
export type PlayerType = 'registered' | 'guest';

export const SKILL_LEVELS: SkillLevel[] = ['LB', 'MB', 'HB', 'LI', 'MI', 'HI', 'A'];

export function skillRangeLabel(min: SkillLevel, max: SkillLevel): string {
  return min === max ? min : `${min} – ${max}`;
}

export interface Player {
  id: string;
  name: string;
  skill_level: SkillLevel;
  phone: string | null;
  is_internal: boolean;
  is_admin: boolean;
  telegram_id: number | null;
  notes: string | null;
}

export interface Venue {
  id: string;
  name: string;
  court_cost_per_hour: number;
  default_pub_fee: number;
}

export interface CourtSlot {
  id: string;
  session_id: string;
  court_label: string;
  from_time: string;
  to_time: string;
  booker_player_id: string;
}

export interface CourtSlotCreate {
  court_label: string;
  from_time: string;
  to_time: string;
  booker_player_id: string;
}

export interface Session {
  id: string;
  date: string;
  start_time: string;
  end_time: string;
  duration_hours: number;
  venue_id: string;
  courts_booked: string;
  num_courts: number;
  min_skill_level: SkillLevel;
  max_skill_level: SkillLevel;
  pub_fee: number;
  max_pax: number;
  status: SessionStatus;
  telegram_message_id: string | null;
  paynow_player_id: string | null;
}

export interface RosterEntry {
  id: string;
  session_id: string;
  player_id: string | null;
  guest_name: string | null;
  position: number;
  is_waitlisted: boolean;
  player_type: PlayerType;
  payment_status: PaymentStatus;
}

export interface ShuttleBatch {
  id: string;
  batch_name: string;
  brand: string;
  cost_per_tube: number;
  shuttles_per_tube: number;
  cost_per_shuttle: number;
  remaining_count: number;
  is_active: boolean;
  owner_label: string | null;
}

export interface BookerReimbursement {
  player_id: string;
  player_name: string;
  amount: number;
}

export interface PnLResult {
  session_id: string;
  total_fees_collected: number;
  court_cost: number;
  shuttle_cost: number;
  net: number;
  external_paid_count: number;
  total_roster_count: number;
  booker_breakdown: BookerReimbursement[];
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "feat: update frontend types for session schema v2

- SkillLevel expanded to 7 values
- Session: min/max skill, duration_hours, string times
- New CourtSlot + CourtSlotCreate + BookerReimbursement
- PnLResult: total_fees_collected (fix field name), booker_breakdown
- Exported SKILL_LEVELS array + skillRangeLabel helper"
```

---

## Task 10: Frontend NewSession — Full Rewrite

**Files:**
- Modify: `frontend/src/pages/NewSession.tsx`

- [ ] **Step 1: Replace `frontend/src/pages/NewSession.tsx`**

```tsx
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { SKILL_LEVELS, type CourtSlotCreate, type Player, type SkillLevel, type Venue } from '../types'

const INPUT_CLASS =
  'w-full rounded-lg bg-gray-800 border border-gray-700 px-4 py-3 text-white focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500'
const LABEL_CLASS = 'block text-sm font-medium text-gray-300 mb-1'

function computeDay(dateStr: string): string {
  if (!dateStr) return ''
  return new Date(dateStr + 'T00:00:00').toLocaleDateString('en-SG', { weekday: 'long' })
}

function computeEndTime(startTime: string, durationHours: number): string {
  if (!startTime) return ''
  const [h, m] = startTime.split(':').map(Number)
  const totalMinutes = h * 60 + m + Math.round(durationHours * 60)
  const endH = Math.floor(totalMinutes / 60) % 24
  const endM = totalMinutes % 60
  return `${String(endH).padStart(2, '0')}:${String(endM).padStart(2, '0')}`
}

interface SlotRow extends CourtSlotCreate {}

export function NewSession() {
  const navigate = useNavigate()
  const [venues, setVenues] = useState<Venue[]>([])
  const [internalPlayers, setInternalPlayers] = useState<Player[]>([])
  const [loadingData, setLoadingData] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const today = new Date().toISOString().split('T')[0]
  const [date, setDate] = useState(today)
  const [startTime, setStartTime] = useState('20:00')
  const [duration, setDuration] = useState(2)
  const [venueId, setVenueId] = useState('')
  const [numCourts, setNumCourts] = useState(2)
  const [courtsBooked, setCourtsBooked] = useState('')
  const [minSkill, setMinSkill] = useState<SkillLevel>('LI')
  const [maxSkill, setMaxSkill] = useState<SkillLevel>('MI')
  const [pubFee, setPubFee] = useState(0)
  const [maxPax, setMaxPax] = useState(12)
  const [maxPaxCustom, setMaxPaxCustom] = useState(false)
  const [paynowPlayerId, setPaynowPlayerId] = useState('')
  const [slots, setSlots] = useState<SlotRow[]>([
    { court_label: '', from_time: '20:00:00', to_time: '22:00:00', booker_player_id: '' },
  ])

  const day = computeDay(date)
  const endTime = computeEndTime(startTime, duration)

  useEffect(() => {
    async function load() {
      try {
        const [venueList, playerList] = await Promise.all([
          api.get<Venue[]>('/api/v1/venues'),
          api.get<Player[]>('/api/v1/players'),
        ])
        setVenues(venueList)
        const internal = playerList.filter((p) => p.is_internal)
        setInternalPlayers(internal)
        if (venueList.length > 0) {
          setVenueId(venueList[0].id)
          setPubFee(venueList[0].default_pub_fee)
        }
        const belle = internal.find((p) => p.name.toLowerCase() === 'belle')
        if (belle) setPaynowPlayerId(belle.id)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load data')
      } finally {
        setLoadingData(false)
      }
    }
    load()
  }, [])

  function handleVenueChange(id: string) {
    setVenueId(id)
    const venue = venues.find((v) => v.id === id)
    if (venue) setPubFee(venue.default_pub_fee)
  }

  function handleNumCourtsChange(val: number) {
    setNumCourts(val)
    if (!maxPaxCustom) setMaxPax(val * 6)
  }

  function handleMaxPaxChange(val: number) {
    setMaxPax(val)
    setMaxPaxCustom(true)
  }

  function addSlot() {
    setSlots((prev) => [
      ...prev,
      {
        court_label: '',
        from_time: startTime + ':00',
        to_time: endTime + ':00',
        booker_player_id: '',
      },
    ])
  }

  function removeSlot(index: number) {
    setSlots((prev) => prev.filter((_, i) => i !== index))
  }

  function updateSlot(index: number, field: keyof SlotRow, value: string) {
    setSlots((prev) => prev.map((s, i) => (i === index ? { ...s, [field]: value } : s)))
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (slots.length === 0) {
      setError('At least one court slot is required')
      return
    }
    setError(null)
    setSubmitting(true)
    try {
      await api.post('/api/v1/sessions', {
        venue_id: venueId,
        date,
        start_time: startTime + ':00',
        duration_hours: duration,
        courts_booked: courtsBooked,
        num_courts: numCourts,
        min_skill_level: minSkill,
        max_skill_level: maxSkill,
        pub_fee: pubFee,
        max_pax: maxPax,
        paynow_player_id: paynowPlayerId || null,
        court_slots: slots,
      })
      navigate('/sessions')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create session')
    } finally {
      setSubmitting(false)
    }
  }

  if (loadingData) return <div className="p-8 text-gray-400">Loading…</div>

  return (
    <div className="max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold text-white mb-6">New Session</h1>
      <form onSubmit={handleSubmit} className="space-y-6">

        {/* Date + Day */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className={LABEL_CLASS}>Date</label>
            <input
              type="date" value={date} required
              onChange={(e) => setDate(e.target.value)}
              className={INPUT_CLASS}
            />
          </div>
          <div>
            <label className={LABEL_CLASS}>Day</label>
            <input type="text" value={day} readOnly
              className={INPUT_CLASS + ' opacity-60 cursor-not-allowed'} />
          </div>
        </div>

        {/* Start Time + Duration + End Time */}
        <div className="grid grid-cols-3 gap-4">
          <div>
            <label className={LABEL_CLASS}>Start Time</label>
            <input
              type="time" value={startTime} required
              onChange={(e) => setStartTime(e.target.value)}
              className={INPUT_CLASS}
            />
          </div>
          <div>
            <label className={LABEL_CLASS}>Duration (hrs)</label>
            <input
              type="number" min="0.5" max="8" step="0.5" value={duration} required
              onChange={(e) => setDuration(parseFloat(e.target.value))}
              className={INPUT_CLASS}
            />
          </div>
          <div>
            <label className={LABEL_CLASS}>End Time</label>
            <input type="text" value={endTime} readOnly
              className={INPUT_CLASS + ' opacity-60 cursor-not-allowed'} />
          </div>
        </div>

        {/* Venue */}
        <div>
          <label className={LABEL_CLASS}>Venue</label>
          <select value={venueId} required
            onChange={(e) => handleVenueChange(e.target.value)}
            className={INPUT_CLASS}>
            {venues.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
          </select>
        </div>

        {/* Num Courts + Courts Booked */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className={LABEL_CLASS}>Num Courts</label>
            <input
              type="number" min="1" value={numCourts} required
              onChange={(e) => handleNumCourtsChange(parseInt(e.target.value))}
              className={INPUT_CLASS}
            />
          </div>
          <div>
            <label className={LABEL_CLASS}>Court Number(s)</label>
            <input
              type="text" placeholder="e.g. Court 3, 4" value={courtsBooked} required
              onChange={(e) => setCourtsBooked(e.target.value)}
              className={INPUT_CLASS}
            />
          </div>
        </div>

        {/* Skill Levels */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className={LABEL_CLASS}>Min Skill Level</label>
            <select value={minSkill}
              onChange={(e) => setMinSkill(e.target.value as SkillLevel)}
              className={INPUT_CLASS}>
              {SKILL_LEVELS.map((l) => <option key={l} value={l}>{l}</option>)}
            </select>
          </div>
          <div>
            <label className={LABEL_CLASS}>Max Skill Level</label>
            <select value={maxSkill}
              onChange={(e) => setMaxSkill(e.target.value as SkillLevel)}
              className={INPUT_CLASS}>
              {SKILL_LEVELS.map((l) => <option key={l} value={l}>{l}</option>)}
            </select>
          </div>
        </div>

        {/* Pub Fee + Max Players */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className={LABEL_CLASS}>Pub Fee ($)</label>
            <input
              type="number" min="0" step="0.5" value={pubFee} required
              onChange={(e) => setPubFee(parseFloat(e.target.value))}
              className={INPUT_CLASS}
            />
          </div>
          <div>
            <label className={LABEL_CLASS}>Max Players</label>
            <input
              type="number" min="1" value={maxPax} required
              onChange={(e) => handleMaxPaxChange(parseInt(e.target.value))}
              className={INPUT_CLASS}
            />
          </div>
        </div>

        {/* PayNow */}
        <div>
          <label className={LABEL_CLASS}>PayNow Recipient</label>
          <select value={paynowPlayerId}
            onChange={(e) => setPaynowPlayerId(e.target.value)}
            className={INPUT_CLASS}>
            <option value="">None</option>
            {internalPlayers.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>

        {/* Court Slots */}
        <div>
          <div className="flex justify-between items-center mb-2">
            <label className={LABEL_CLASS + ' mb-0'}>Court Slots</label>
            <button type="button" onClick={addSlot}
              className="text-sm text-brand-400 hover:text-brand-300">
              + Add Slot
            </button>
          </div>
          {slots.length === 0 && (
            <p className="text-red-400 text-sm mb-2">At least one court slot is required.</p>
          )}
          <div className="space-y-3">
            {slots.map((slot, i) => (
              <div key={i}
                className="grid grid-cols-4 gap-2 items-end p-3 rounded-lg bg-gray-900 border border-gray-700">
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Court</label>
                  <input type="text" placeholder="Court 1" value={slot.court_label} required
                    onChange={(e) => updateSlot(i, 'court_label', e.target.value)}
                    className={INPUT_CLASS} />
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">From</label>
                  <input type="time" value={slot.from_time.slice(0, 5)} required
                    onChange={(e) => updateSlot(i, 'from_time', e.target.value + ':00')}
                    className={INPUT_CLASS} />
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">To</label>
                  <input type="time" value={slot.to_time.slice(0, 5)} required
                    onChange={(e) => updateSlot(i, 'to_time', e.target.value + ':00')}
                    className={INPUT_CLASS} />
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Booker</label>
                  <div className="flex gap-1">
                    <select value={slot.booker_player_id} required
                      onChange={(e) => updateSlot(i, 'booker_player_id', e.target.value)}
                      className={INPUT_CLASS}>
                      <option value="">Select</option>
                      {internalPlayers.map((p) => (
                        <option key={p.id} value={p.id}>{p.name}</option>
                      ))}
                    </select>
                    {slots.length > 1 && (
                      <button type="button" onClick={() => removeSlot(i)}
                        className="text-red-400 hover:text-red-300 px-2 shrink-0">
                        ✕
                      </button>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {error && <p className="text-red-400 text-sm">{error}</p>}

        <button
          type="submit"
          disabled={submitting || slots.length === 0}
          className="w-full bg-brand-600 hover:bg-brand-500 text-white font-semibold py-3 px-6 rounded-lg transition disabled:opacity-50">
          {submitting ? 'Creating…' : 'Create Session'}
        </button>
      </form>
    </div>
  )
}
```

- [ ] **Step 2: Verify the frontend builds without TypeScript errors**

```bash
cd frontend
npm run build 2>&1 | tail -20
```

Expected: `✓ built in` (no TS errors)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/NewSession.tsx
git commit -m "feat: rewrite NewSession form for schema v2

- date field with computed day display
- start_time + duration + computed end_time
- num_courts drives max_pax default (overridable)
- min/max skill level selectors (7 values)
- court slots dynamic table (required, min 1)
- paynow defaults to 'belle' if found in internal players"
```

---

## Task 11: Frontend SessionDetail, Sessions, PnL

**Files:**
- Modify: `frontend/src/pages/Sessions.tsx`
- Modify: `frontend/src/pages/SessionDetail.tsx`
- Modify: `frontend/src/pages/PnL.tsx`

- [ ] **Step 1: Update `Sessions.tsx` — skill range display**

In `Sessions.tsx`, find the `SKILL_LABELS` constant and the line using it:

```typescript
const SKILL_LABELS: Record<string, string> = {
  HB: 'High Beginner',
  LI: 'Low Intermediate',
  MB: 'Mid Beginner',
}
```

Replace the entire `SKILL_LABELS` block with the import of the shared helper:

```typescript
import { skillRangeLabel } from '../types'
```

Then find this line in the JSX:

```tsx
{SKILL_LABELS[session.skill_level]} · {session.courts_booked} courts · max {session.max_pax}
```

Replace with:

```tsx
{skillRangeLabel(session.min_skill_level, session.max_skill_level)} · {session.courts_booked} · max {session.max_pax}
```

- [ ] **Step 2: Update `SessionDetail.tsx` — skill range + fix SKILL_LABELS**

In `SessionDetail.tsx`, locate the `SKILL_LABELS` constant at the top and the JSX line that uses `session.skill_level`:

Old constant (remove entirely):
```typescript
const SKILL_LABELS: Record<string, string> = {
  HB: 'High Beginner',
  LI: 'Low Intermediate',
  MB: 'Mid Beginner',
}
```

Add the import at the top of the file imports section:
```typescript
import { skillRangeLabel } from '../types'
```

Find the JSX line:
```tsx
<span>Level: <span className="text-gray-200">{SKILL_LABELS[session.skill_level]}</span></span>
```

Replace with:
```tsx
<span>Level: <span className="text-gray-200">{skillRangeLabel(session.min_skill_level, session.max_skill_level)}</span></span>
```

- [ ] **Step 3: Update `PnL.tsx` — fix field name + show booker breakdown**

In `PnL.tsx`, find all occurrences of `pnl.total_income` and replace with `pnl.total_fees_collected`:

```typescript
// Line ~76:
const totalIncome = items.reduce((sum, { pnl }) => sum + pnl.total_fees_collected, 0)
```

```tsx
// Line ~157 (in the card JSX):
Income ${pnl.total_fees_collected.toFixed(2)} · Costs $
```

Then locate the P&L card JSX (the line showing income/costs) and add booker breakdown below it:

```tsx
{pnl.booker_breakdown.length > 0 && (
  <div className="mt-2 text-xs text-gray-400 space-y-0.5">
    <span className="font-medium text-gray-300">Court reimbursements:</span>
    {pnl.booker_breakdown.map((b) => (
      <div key={b.player_id} className="flex justify-between">
        <span>{b.player_name}</span>
        <span>${b.amount.toFixed(2)}</span>
      </div>
    ))}
  </div>
)}
```

- [ ] **Step 4: Build to verify no TypeScript errors**

```bash
cd frontend
npm run build 2>&1 | tail -20
```

Expected: `✓ built in` (no TS errors)

- [ ] **Step 5: Run all backend tests one final time**

```bash
cd backend
pytest tests/ -v
```

Expected: All tests PASS

- [ ] **Step 6: Final commit**

```bash
git add frontend/src/pages/Sessions.tsx frontend/src/pages/SessionDetail.tsx frontend/src/pages/PnL.tsx
git commit -m "feat: update frontend pages for session schema v2

- Sessions/SessionDetail: show min–max skill range via skillRangeLabel()
- PnL: fix total_income → total_fees_collected; show booker_breakdown table"
```

---

## Acceptance Verification

After all tasks are complete, verify each acceptance criterion from the spec:

```bash
# 1. Backend tests all pass
cd backend && pytest tests/ -v

# 2. Frontend builds without errors
cd frontend && npm run build

# 3. Manual smoke test — create a session via API (requires running backend)
curl -X POST http://localhost:8000/api/v1/sessions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "venue_id": "<venue_id>",
    "date": "2026-06-01",
    "start_time": "20:00:00",
    "duration_hours": 2.0,
    "courts_booked": "Court 3, 4",
    "num_courts": 2,
    "min_skill_level": "LI",
    "max_skill_level": "MI",
    "pub_fee": 12.0,
    "court_slots": [
      {"court_label": "Court 3", "from_time": "20:00:00", "to_time": "22:00:00", "booker_player_id": "<player_id>"},
      {"court_label": "Court 4", "from_time": "20:00:00", "to_time": "22:00:00", "booker_player_id": "<player_id>"}
    ]
  }'
# Expected: 201 with session including end_time: "22:00:00" (GENERATED)
```

Checklist:
- [ ] `POST /api/v1/sessions` returns 201 (no 422)
- [ ] `end_time` in response is correctly computed (start_time + duration_hours)
- [ ] `GET /api/v1/sessions/{id}/pnl` returns `booker_breakdown` list
- [ ] Telegram announcement shows `🎯 Level: LI – MI`
- [ ] NewSession form renders: day auto-fills, end time auto-fills, court slots table present
- [ ] Sessions list shows skill range (e.g. `LI – MI`)
