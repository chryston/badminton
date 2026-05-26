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
| Q2 | Duration storage | Store `duration_hours numeric` in DB for convenience |
| Q3 | max_pax | Auto-default `num_courts × 6` in service layer, overridable by admin |
| Q4 | Booker | Structured `court_slots` table with FK to `players` (for P&L cost attribution) |
| Q5 | courts_booked vs num_courts | Keep both: `num_courts int` (count) + `courts_booked text` (e.g. "Court 3, 4") |
| Q6 | Court slots required? | Yes — at least 1 court slot required when creating a session |

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
| `duration_hours` | **ADDED** `numeric NOT NULL` | e.g. 2.0 — stored for convenience |
| `courts_booked` | unchanged | text field, e.g. "Court 3, 4" |
| `num_courts` | unchanged | integer count of courts |
| `max_pax` | unchanged | integer, defaults to `num_courts × 6` in service |
| `start_time` | unchanged | time |
| `end_time` | unchanged | time — computed from start_time + duration_hours in service |

### 4.2 `court_slots` — NEW TABLE

```sql
CREATE TABLE court_slots (
    id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id          uuid        NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    court_label         text        NOT NULL,  -- e.g. "Court 1"
    from_time           time        NOT NULL,
    to_time             time        NOT NULL,
    booker_player_id    uuid        NOT NULL REFERENCES players(id),
    created_at          timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT court_slot_time_order CHECK (to_time > from_time)
);
CREATE INDEX ON court_slots(session_id);
```

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

Steps (idempotent):
1. Add `min_skill_level`, `max_skill_level`, `duration_hours` to `sessions`
2. Migrate existing `skill_level` data → both min and max get old value if it maps, else `'LI'`
3. Drop `skill_level` from `sessions`
4. Update `players.skill_level` CHECK constraint
5. Create `court_slots` table + index + RLS policy

---

## 5. Backend Changes

### 5.1 Models (`backend/app/models/session.py`)

**`SessionCreate`** (what the API receives):
```python
class SessionCreate(BaseModel):
    venue_id: UUID
    date: date
    start_time: time
    duration_hours: float = 2.0       # NEW — used to compute end_time
    courts_booked: str                 # text, e.g. "Court 3, 4"
    num_courts: int = 1
    min_skill_level: str = "LI"       # replaces skill_level
    max_skill_level: str = "MI"       # NEW
    pub_fee: float
    max_pax: int | None = None        # None → service computes num_courts × 6
    paynow_player_id: UUID | None = None
    court_slots: list[CourtSlotCreate]  # required, min length 1
```

**`Session`** (DB representation):
```python
class Session(BaseModel):
    id: UUID
    venue_id: UUID
    date: date
    start_time: time
    end_time: time                    # stored after computation
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
- Compute `end_time = start_time + duration_hours`
- Compute `max_pax = data.max_pax if data.max_pax is not None else data.num_courts * 6`
- After inserting session row, bulk-insert `court_slots` rows (same transaction via sequential inserts — Supabase doesn't expose multi-table transactions directly; insert slots after session, clean up session if slots fail)
- Validate: `len(data.court_slots) >= 1` (raise ValueError if empty)
- Continue to auto-add internal players as `verified_paid` roster entries

**New `court_slot_service.py`**:
- `get_by_session(session_id)` → list[CourtSlot]
- `add_slot(session_id, data: CourtSlotCreate)` → CourtSlot
- `remove_slot(slot_id)` → None

**`pnl_service.calculate()`** changes:
- Remove old `court_cost = cost_per_hour × hours × num_courts`
- New: `court_cost = sum(cost_per_hour × (slot.to_time - slot.from_time).seconds/3600 for slot in court_slots)`
- `get_session_pnl()` fetches court_slots for the session and passes to `calculate()`
- Add `booker_breakdown: list[{player_id, name, amount}]` to `PnLResult` — shows each booker's reimbursement amount

### 5.3 Router changes

**`sessions.py`** — no endpoint changes; `SessionCreate` model change is transparent.

**New `backend/app/routers/court_slots.py`**:
```
GET    /sessions/{id}/court-slots           → court_slot_service.get_by_session(id)
POST   /sessions/{id}/court-slots           → court_slot_service.add_slot(id, data)  [201]
DELETE /sessions/{id}/court-slots/{slot_id} → court_slot_service.remove_slot(slot_id) [204]
```

All routes require `require_admin`.

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
2. Session is created with `start_time`, `end_time` (computed), `duration_hours`, `min_skill_level`, `max_skill_level`
3. Court slots are created atomically with the session (if slot insert fails, session is rolled back or cleaned up)
4. `GET /api/v1/sessions/{id}/pnl` returns correct `court_cost` using slot-based calculation and `booker_breakdown`
5. Telegram announcement shows `🎯 Level: LI – MI` (or single level if same)
6. `players.skill_level` CHECK constraint accepts all 7 new values
7. Existing players with `HB/LI/MB` remain valid (all three are in the new set)
8. `NewSession` form: day auto-fills from date, end time auto-fills from start + duration, max_pax auto-fills from num_courts × 6

---

## 9. Migration Safety

- `skill_level IN ('HB','LI','MB')` is a subset of the new 7-value set — existing player records remain valid
- Session `skill_level` column: existing rows migrated to `min_skill_level = max_skill_level = old_skill_level` (or `'LI'` if old value was `'HB - LI'` composite string)
- Migration is idempotent (uses `IF NOT EXISTS`, `IF EXISTS`, `ON CONFLICT DO NOTHING`)

---

## 10. Out of Scope

- Editing court slots on the `NewSession` page after creation (managed from `SessionDetail`)
- Cost splitting between bookers (P&L shows amounts but does not create payment records)
- Bulk import of historical court slots from Excel
