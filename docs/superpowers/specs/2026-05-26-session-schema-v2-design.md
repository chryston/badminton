# Session Schema V2 — Design Spec

**Date:** 2026-05-26  
**Status:** Approved for implementation  
**Scope:** Session schema refactor — DB migration, backend models/services, frontend form, P&L, Telegram bot

---

## 1. Problem Statement

The current session creation form sends `{date, time, venue_id, courts_booked (int), skill_level, pub_fee, max_pax}` but the backend `SessionCreate` model expects `{start_time, end_time, courts_booked (str), num_courts, skill_level}`. This mismatch causes a 422 error on every session creation.

Beyond the immediate bug, the schema needs several structural improvements:

- A single `skill_level` field is insufficient; sessions should define a skill range (`min_skill_level` to `max_skill_level`)
- There is no structured way to track which internal member booked which court for which hours (needed for P&L cost reimbursement)
- `duration` is useful to store so admins don't have to compute end time manually
- `max_pax` should auto-default from `num_courts × 6`

---

## 2. Decisions Made

| # | Question | Decision |
|---|---|---|
| Q1 | Skill level architecture | CHECK constraint (not lookup table) — levels are stable, migrations are rare |
| Q2 | Duration storage | Store `duration_hours numeric` in DB; `end_time` is a `GENERATED ALWAYS AS` column (drift-free) |
| Q3 | max_pax | Auto-default `num_courts × 6` in service layer, overridable by admin |
| Q4 | Booker | Structured `court_slots` table with FK to `players` (for P&L cost attribution) |
| Q5 | courts_booked vs num_courts | Keep both: `num_courts int` (count) + `courts_booked text` (e.g. "Court 3, 4") |
| Q6 | Court slots required? | Yes — at least 1 court slot required when creating a session |
| D1 | num_courts redundancy | Keep `num_courts` — admin sets it; no automated derivation from slots |
| D2 | end_time consistency | `end_time GENERATED ALWAYS AS (start_time + make_interval(hours => duration_hours))` — never drifts |
| D3 | Court slot time columns | Use `time` (HH:MM) — badminton sessions never cross midnight |
| D4 | Session + slots atomicity | Supabase RPC `create_session_with_slots` wraps both inserts in one PG transaction |

---

## 3. Skill Level Values

Expanded from `HB, LI, MB` to:

```
LB  — Low Beginner
MB  — Mid Beginner
HB  — High Beginner
LI  — Low Intermediate
MI  — Mid Intermediate
HI  — High Intermediate
A   — Advanced
```

Applied as `CHECK` constraints on:
- `players.skill_level`
- `sessions.min_skill_level`
- `sessions.max_skill_level`

---

## 4. Database Schema Changes

### 4.1 `sessions` table — column changes

| Column | Change | Notes |
|---|---|---|
| `skill_level` | **REMOVED** | Replaced by min/max |
| `min_skill_level` | **ADDED** `text NOT NULL` | CHECK ('LB','MB','HB','LI','MI','HI','A') |
| `max_skill_level` | **ADDED** `text NOT NULL` | CHECK ('LB','MB','HB','LI','MI','HI','A') |
| `duration_hours` | **ADDED** `numeric NOT NULL` | e.g. 2.0 — stored directly; drives `end_time` |
| `end_time` | **CHANGED to GENERATED** | `GENERATED ALWAYS AS (start_time + make_interval(hours => duration_hours::int)) STORED` |
| `courts_booked` | unchanged | text field, e.g. "Court 3, 4" |
| `num_courts` | unchanged | integer count of courts |
| `max_pax` | unchanged | integer, defaults to `num_courts × 6` in service |
| `start_time` | unchanged | time |

> **Note:** `end_time` is now computed by the DB from `start_time + duration_hours`. It cannot be set independently. `make_interval` takes an integer hours argument; `duration_hours` must be cast to `int` in the generated expression (fractional hours not supported via `make_interval(hours=>)` in PG — use `(duration_hours * interval '1 hour')` instead for fractional support).

The actual GENERATED expression:
```sql
end_time time GENERATED ALWAYS AS (
    (start_time::text::interval + (duration_hours * interval '1 hour'))::time
) STORED
```

### 4.2 `court_slots` — NEW TABLE

```sql
CREATE TABLE court_slots (
    id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id          uuid        NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    court_label         text        NOT NULL,  -- e.g. "Court 1"
    from_time           time        NOT NULL,
    to_time             time        NOT NULL,
    booker_player_id    uuid        NOT NULL REFERENCES players(id) ON DELETE RESTRICT,
    created_at          timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT court_slot_time_order CHECK (to_time > from_time)
);
CREATE INDEX ON court_slots(session_id);
```

**`ON DELETE RESTRICT` on `booker_player_id`:** Prevents deleting a player who has booked court slots — admin must reassign slots first.

**RLS:** Same policy as other tables — service role bypasses, authenticated users read-only.

### 4.3 `players` table — CHECK constraint update

```sql
ALTER TABLE players 
  DROP CONSTRAINT IF EXISTS players_skill_level_check,
  ADD CONSTRAINT players_skill_level_check 
    CHECK (skill_level IN ('LB','MB','HB','LI','MI','HI','A'));
```

### 4.4 Migration file

New file: `supabase/migrations/005_session_schema_v2.sql`

Steps (fully idempotent — all steps guarded with `IF NOT EXISTS` / `IF EXISTS` / column existence checks):

1. **Add `min_skill_level`, `max_skill_level`** to `sessions` (if not exists), nullable first
2. **Add `duration_hours`** to `sessions` (if not exists), nullable first; backfill with `2.0` for all existing rows
3. **Data migration** — only runs if `skill_level` column still exists:
   - `'HB - LI'` composite string → `min='HB', max='LI'` (correct semantic split)
   - Any other single value (e.g. `'LI'`) → `min=value, max=value`
   - Default fallback: `min='LI', max='MI'`
4. **Drop `skill_level`** from `sessions` (if exists)
5. **Add NOT NULL constraints** on `min_skill_level`, `max_skill_level`, `duration_hours`
6. **Add CHECK constraints** on min/max skill level columns
7. **Change `end_time`** to `GENERATED ALWAYS AS` column (requires drop + re-add in PG):
   - Drop old `end_time` column
   - Add `end_time time GENERATED ALWAYS AS ((start_time + (duration_hours * interval '1 hour'))::time) STORED`
8. **Update `players.skill_level` CHECK constraint** to include all 7 values
9. **Create `court_slots` table**, index, and RLS policy (if not exists)
10. **Create RPC** `create_session_with_slots(session_data jsonb, slots_data jsonb)` — atomic PG function

> **Idempotency note:** Step 3 is guarded with `IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='sessions' AND column_name='skill_level')`. On re-run, the data migration is skipped entirely.

---

## 5. Backend Changes

### 5.1 Models (`backend/app/models/session.py`)

**`SessionCreate`** (what the API receives):
```python
class CourtSlotCreate(BaseModel):
    court_label: str
    from_time: time
    to_time: time
    booker_player_id: UUID

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
    max_pax: Annotated[int, Field(gt=0)] | None = None  # None → num_courts × 6
    paynow_player_id: UUID | None = None
    court_slots: Annotated[list[CourtSlotCreate], Field(min_length=1)]  # required, min 1
```

**`SessionUpdate`** (for PATCH — all fields optional):
```python
class SessionUpdate(BaseModel):
    date: date | None = None
    start_time: time | None = None
    duration_hours: float | None = None   # NOTE: updating duration_hours recomputes end_time automatically
    courts_booked: str | None = None
    num_courts: int | None = None
    min_skill_level: str | None = None
    max_skill_level: str | None = None
    pub_fee: float | None = None
    max_pax: Annotated[int, Field(gt=0)] | None = None
    paynow_player_id: UUID | None = None
    shuttles_used: int | None = None
    status: str | None = None
```

**`Session`** (DB representation — `end_time` is read from DB, not set by service):
```python
class Session(BaseModel):
    id: UUID
    venue_id: UUID
    date: date
    start_time: time
    end_time: time          # DB GENERATED — always consistent with start_time + duration_hours
    duration_hours: float
    courts_booked: str
    num_courts: int
    min_skill_level: str
    max_skill_level: str
    pub_fee: float
    max_pax: int
    status: str
    telegram_message_id: int | None = None
    paynow_player_id: UUID | None = None
    created_at: datetime
```

**New models** (`backend/app/models/court_slot.py`):
```python
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

### 5.2 Services

**`session_service.create()`** changes:
- Remove: manual `end_time` computation (now DB-generated)
- Compute `max_pax = data.max_pax if data.max_pax is not None else data.num_courts * 6`
- Call RPC `create_session_with_slots(session_data, slots_data)` instead of two sequential inserts
- The RPC handles atomicity — if slot insert fails, session is rolled back in the same transaction
- Continue to auto-add internal players as `verified_paid` roster entries after session creation

**New `court_slot_service.py`**:
- `get_by_session(session_id)` → list[CourtSlot]
- `add_slot(session_id, data: CourtSlotCreate)` → CourtSlot
- `remove_slot(slot_id)` → None

**`pnl_service.calculate()`** changes:
- Signature: `calculate(session, venue, court_slots, booker_names: dict[UUID, str], shuttles_used, active_batch)` — pure function
- Remove old `court_cost = cost_per_hour × hours × num_courts`
- New: `court_cost = sum(cost_per_hour × slot_duration_hours for slot in court_slots)` where `slot_duration_hours = (slot.to_time hour - slot.from_time hour)` as float
- `booker_breakdown`: group slots by `booker_player_id`, sum cost per booker, resolve names from `booker_names` dict

**`pnl_service.get_session_pnl()`** changes:
- Pre-fetch court slots: `court_slots = await court_slot_service.get_by_session(session_id)`
- Pre-resolve booker names: `booker_names = {s.booker_player_id: player_name for s in court_slots}` (one SELECT on players table)
- Pass both into `calculate(..., court_slots=court_slots, booker_names=booker_names, ...)`

### 5.3 Router changes

**`sessions.py`** — no endpoint changes; `SessionCreate` model change is transparent. `create_session` endpoint calls `session_service.create()` which now calls the RPC.

**New `backend/app/routers/court_slots.py`**:
```
GET    /sessions/{id}/court-slots           → court_slot_service.get_by_session(id)
POST   /sessions/{id}/court-slots           → court_slot_service.add_slot(id, data)  [201]
DELETE /sessions/{id}/court-slots/{slot_id} → court_slot_service.remove_slot(slot_id) [204]
```

All routes require `require_admin`.

**`main.py`** — wire new router: `app.include_router(court_slots.router, prefix="/api/v1", tags=["court-slots"])`

### 5.4 Bot message formatter

Update `format_session_announcement()`:
- Replace `🎯 Level: {session.skill_level}` with `🎯 Level: {session.min_skill_level} – {session.max_skill_level}`
- When min == max, show just one level

---

## 6. Frontend Changes

### 6.1 `src/types/index.ts`

- Update `Session` type: remove `skill_level`, add `min_skill_level`, `max_skill_level`, `duration_hours`
- Update `SkillLevel` type: `'LB' | 'MB' | 'HB' | 'LI' | 'MI' | 'HI' | 'A'`
- Add `CourtSlot` and `CourtSlotCreate` interfaces

### 6.2 `src/pages/NewSession.tsx` — full rewrite

Form fields (in order):
1. **Date** (date picker) + **Day** (read-only, computed: "Monday" etc.)
2. **Start Time** (time input, default `20:00`) + **Duration** (number, default `2`) + **End Time** (read-only, computed)
3. **Venue** (select, auto-fills pub_fee from `venue.default_pub_fee`)
4. **Num Courts** (number, default `2`) + **Courts Booked** (text, e.g. "Court 3, 4")
5. **Min Skill Level** (select) + **Max Skill Level** (select)
6. **Pub Fee** (number, auto-filled, editable)
7. **Max Players** (number, default `num_courts × 6`, editable)
8. **PayNow Player** (select from internal players, default: player named "Belle" if present)
9. **Court Slots** (dynamic table — required, min 1 row):
   - Each row: Court Label (text) | From (time) | To (time) | Booker (select from internal players) | ✕ remove
   - "+ Add Slot" button
   - Validation: at least 1 slot, to_time > from_time per row

Submit payload:
```json
{
  "venue_id": "...",
  "date": "2026-05-26",
  "start_time": "20:00:00",
  "duration_hours": 2.0,
  "courts_booked": "Court 3, 4",
  "num_courts": 2,
  "min_skill_level": "LI",
  "max_skill_level": "MI",
  "pub_fee": 12,
  "max_pax": 12,
  "paynow_player_id": "...",
  "court_slots": [
    {"court_label": "Court 3", "from_time": "20:00:00", "to_time": "22:00:00", "booker_player_id": "..."},
    {"court_label": "Court 4", "from_time": "20:00:00", "to_time": "22:00:00", "booker_player_id": "..."}
  ]
}
```

### 6.3 `src/pages/SessionDetail.tsx`

- Show skill range: "LI – MI" (or single level if same)
- Add **Court Slots** section (read-only for published/completed, editable for internal):
  - Table showing each slot: court, from, to, booker name
  - "Add Slot" + remove buttons for `internal` status sessions
- P&L section: show `booker_breakdown` with individual reimbursement amounts

### 6.4 `src/pages/Sessions.tsx`

- Session card: show `{min_skill_level}–{max_skill_level}` instead of `skill_level`

---

## 7. P&L Calculation Update

**Old formula:**
```
court_cost = venue.court_cost_per_hour × hours × num_courts
```

**New formula:**
```
court_cost = Σ (venue.court_cost_per_hour × slot_duration_hours) for each court_slot
booker_breakdown = group by booker_player_id, sum each booker's slot costs
```

The court cost is the same total (assuming slots cover the full session), but now attributable per booker.

**`PnLResult` model addition:**
```python
class BookerReimbursement(BaseModel):
    player_id: UUID
    player_name: str
    amount: float

class PnLResult(BaseModel):
    total_income: float
    court_cost: float
    shuttle_cost: float
    net: float
    external_paid_count: int
    shuttles_used: int
    booker_breakdown: list[BookerReimbursement] = []  # NEW
```

---

## 8. Acceptance Criteria

1. `POST /api/v1/sessions` succeeds without 422 error when correct payload is sent
2. Session is created with `start_time`, `duration_hours`, `min_skill_level`, `max_skill_level`; `end_time` is computed by DB and returned correctly
3. Court slots are created atomically via RPC — if slot insert fails, the session row does not persist
4. `GET /api/v1/sessions/{id}/pnl` returns correct `court_cost` using slot-based calculation and `booker_breakdown` with player names
5. Telegram announcement shows `🎯 Level: LI – MI` (or single level if same)
6. `players.skill_level` CHECK constraint accepts all 7 new values
7. Existing players with `HB/LI/MB` remain valid (all three are in the new set)
8. `NewSession` form: day auto-fills from date, end time auto-fills from start + duration, max_pax auto-fills from num_courts × 6
9. All existing tests pass after model updates; E2E test uses new `SessionCreate` payload with `court_slots`

---

## 9. Migration Safety

- `skill_level IN ('HB','LI','MB')` is a subset of the new 7-value set — existing player records remain valid
- Session `skill_level` data migration:
  - `'HB - LI'` → `min_skill_level='HB', max_skill_level='LI'` (correct semantic split)
  - Any other single value (e.g. `'LI'`) → `min_skill_level=value, max_skill_level=value`
  - Unknown values → `min='LI', max='MI'` fallback
- `duration_hours` backfill: all existing sessions get `2.0` before NOT NULL constraint is applied
- `end_time` column change: existing `end_time` values are dropped and regenerated from `start_time + duration_hours`
- Migration is idempotent: step 3 (data migration) is guarded by `IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='sessions' AND column_name='skill_level')`

## 10. Test Update Plan

The following test files use the old `Session`/`SessionCreate` model and must be updated:

| File | Change required |
|---|---|
| `test_session_flow_e2e.py` | Update `SessionCreate` payload: add `duration_hours`, `court_slots`, replace `skill_level` with `min_skill_level`/`max_skill_level`. Remove manual `end_time`. |
| `test_pnl_service.py` | Update `Session` fixture: add `duration_hours`, replace `skill_level`. Update `calculate()` calls to pass `court_slots` and `booker_names` dict. |
| `test_message_formatter.py` | Update `Session` fixture: replace `skill_level` with `min_skill_level`/`max_skill_level`. Add assertions for `LI – MI` format. |

Add one new test: `test_court_slot_service.py` — covers `get_by_session`, `add_slot`, `remove_slot` with minimal Supabase mock.

---

## 10. Out of Scope

- Editing court slots on the `NewSession` page after creation (managed from `SessionDetail`)
- Cost splitting between bookers (P&L shows amounts but does not create payment records)
- Bulk import of historical court slots from Excel
