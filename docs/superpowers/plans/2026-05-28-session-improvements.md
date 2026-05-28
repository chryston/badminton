# Session Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 9 session management improvements: empty roster on create, inline session editing, skill level defaults, verify-any-payment, cancel session with bot notification, loading spinner, Telegram court label, 422 complete-session fix, and internal players auto-verified at $0.

**Architecture:** Backend fixes are isolated to model/service/router/bot layers; frontend fixes are in SessionDetail.tsx and Sessions.tsx. One new DB migration adds `cancelled` status. No new DB tables.

**Tech Stack:** FastAPI + Pydantic v2, Supabase (PostgreSQL), React + TypeScript + Tailwind, python-telegram-bot

**Spec:** `docs/superpowers/specs/2026-05-28-session-improvements-design.md`

---

## Wave execution order

| Wave | Tasks (parallel) | Depends on |
|------|-----------------|------------|
| 1 | Task 1 (DB + backend models/services), Task 2 (frontend types + simple fixes) | — |
| 2 | Task 3 (cancel backend), Task 4 (frontend edit) | Task 1 |
| 3 | Task 5 (bot formatter + cancel), Task 6 (frontend cancel UI) | Task 3 |

---

## Task 1: DB migration + backend model/service fixes

**Items covered:** 1 (empty roster), 3 (skill defaults), 9 (auto-pay internal), DB (cancelled status + payment_status constraint)

**Files:**
- Create: `supabase/migrations/006_add_cancelled_status.sql`
- Modify: `backend/app/models/session.py`
- Modify: `backend/app/services/session_service.py`
- Modify: `backend/app/services/roster_service.py`
- Test: `backend/tests/test_roster_service.py` (new file)

---

- [ ] **Step 1: Write failing tests for roster_service internal-player auto-pay**

Create `backend/tests/test_roster_service.py`:

```python
from unittest.mock import MagicMock, patch
from uuid import uuid4
from app.services import roster_service
from app.models.player import Player
from app.models.roster import RosterEntry
from datetime import datetime, timezone


def _make_player(is_internal: bool) -> Player:
    return Player(
        id=uuid4(),
        name="Test Player",
        skill_level="LI",
        phone=None,
        is_internal=is_internal,
        telegram_id=123456,
        notes=None,
        created_at=datetime.now(timezone.utc),
    )


def _make_db_client():
    """Build a minimal mock DB client — only mocks the insert().execute() chain.

    The insert side_effect echoes back the inserted row so assertions on the
    returned RosterEntry reflect what the code actually set.
    """
    client = MagicMock()
    now = datetime.now(timezone.utc).isoformat()

    def _insert_and_return(row):
        mock = MagicMock()
        mock.execute.return_value.data = [
            {"id": str(uuid4()), "guest_name": None, "is_waitlisted": False,
             "joined_at": now, "created_at": now, **row}
        ]
        return mock

    client.table.return_value.insert.side_effect = _insert_and_return
    return client


def test_external_player_added_as_unpaid():
    """External players join with payment_status='unpaid'."""
    player = _make_player(is_internal=False)
    client = _make_db_client()
    with (
        patch("app.services.roster_service.get_service_client", return_value=client),
        patch("app.services.player_service.get_by_telegram_id", return_value=None),
        patch("app.services.player_service.create", return_value=player),
        patch("app.services.roster_service.get_active_count", return_value=0),
    ):
        entry, _ = roster_service.add_player(uuid4(), 123456, "External Player")
    assert entry.payment_status == "unpaid"


def test_internal_player_auto_marked_verified_paid():
    """Internal players are automatically marked verified_paid when they join."""
    player = _make_player(is_internal=True)
    client = _make_db_client()
    with (
        patch("app.services.roster_service.get_service_client", return_value=client),
        patch("app.services.player_service.get_by_telegram_id", return_value=None),
        patch("app.services.player_service.create", return_value=player),
        patch("app.services.roster_service.get_active_count", return_value=0),
    ):
        entry, _ = roster_service.add_player(uuid4(), 123456, "Internal Player")
    assert entry.payment_status == "verified_paid"
```

- [ ] **Step 2: Run to confirm tests fail**

```bash
cd backend && python -m pytest tests/test_roster_service.py -v
```

Expected: `FAILED test_internal_player_auto_marked_verified_paid` (current code always sets `"unpaid"`)

- [ ] **Step 3: Write DB migration**

Create `supabase/migrations/006_add_cancelled_status.sql`:

```sql
-- Migration 006: Add cancelled session status, cancellation_reason, fix payment_status constraint

-- ── 1. Expand sessions.status to include 'cancelled' ─────────────────────────
ALTER TABLE sessions
    DROP CONSTRAINT IF EXISTS sessions_status_check,
    ADD  CONSTRAINT sessions_status_check
        CHECK (status IN ('internal', 'published', 'completed', 'cancelled'));

-- ── 2. Add cancellation_reason column ─────────────────────────────────────────
ALTER TABLE sessions
    ADD COLUMN IF NOT EXISTS cancellation_reason TEXT;

-- ── 3. Fix roster_entries.payment_status to include 'pending_verification' ───
--      (001_schema.sql only had unpaid/verified_paid — inconsistent with app)
ALTER TABLE roster_entries
    DROP CONSTRAINT IF EXISTS roster_entries_payment_status_check,
    ADD  CONSTRAINT roster_entries_payment_status_check
        CHECK (payment_status IN ('unpaid', 'pending_verification', 'verified_paid'));
```

- [ ] **Step 4: Update backend/app/models/session.py — change defaults + add venue_id to SessionUpdate**

In `SessionCreate`, change defaults:
```python
min_skill_level: SkillLevelStr = "HB"   # was "LI"
max_skill_level: SkillLevelStr = "LI"   # was "MI"
```

In `SessionUpdate`, add `venue_id` field after the existing fields:
```python
class SessionUpdate(BaseModel):
    venue_id: UUID | None = None          # ← ADD THIS
    date: _date | None = None
    start_time: _time | None = None
    duration_hours: float | None = None
    courts_booked: str | None = None
    num_courts: int | None = None
    min_skill_level: SkillLevelStr | None = None
    max_skill_level: SkillLevelStr | None = None
    pub_fee: float | None = None
    max_pax: Annotated[int, Field(gt=0)] | None = None
    paynow_player_id: UUID | None = None
    telegram_message_id: int | None = None
```

Also add `cancellation_reason` to the `Session` read model:
```python
class Session(BaseModel):
    # ... existing fields ...
    cancellation_reason: str | None = None   # ← ADD at end of class
```

Also fix `session_service.update()` to use `exclude_unset=True` instead of `exclude_none=True`. This allows clearing nullable fields (e.g., `paynow_player_id: null` will clear it):
```python
# In update() function, change:
payload = data.model_dump(mode="json", exclude_none=True)
# To:
payload = data.model_dump(mode="json", exclude_unset=True)
```

- [ ] **Step 5: Update backend/app/services/session_service.py — remove auto-populate roster**

In `create()`, delete the entire block that auto-populates internal players (lines ~62–77):

```python
# DELETE this entire block:
internal_result = (
    client.table("players").select("*").eq("is_internal", True).order("name").execute()
)
if internal_result.data:
    now = datetime.now(timezone.utc).isoformat()
    roster_rows = [...]
    client.table("roster_entries").insert(roster_rows).execute()
```

Also remove the unused `datetime` import from `session_service.py` if it's only used there (check first).

- [ ] **Step 6: Update backend/app/services/roster_service.py — internal player auto-pay**

In `add_player()`, find the `row` dict construction and change payment_status:

```python
# Find the player's is_internal flag before building the row.
# player is already fetched above via player_service.get_by_telegram_id / player_service.create

row = {
    "session_id": str(session_id),
    "player_id": str(player.id),
    "player_type": "registered",
    "payment_status": "verified_paid" if player.is_internal else "unpaid",  # ← CHANGE
    "is_waitlisted": is_waitlisted,
    "position": next_position,
    "joined_at": now,
}
```

- [ ] **Step 7: Run tests to confirm both pass**

```bash
cd backend && python -m pytest tests/test_roster_service.py -v
```

Expected: `PASSED test_external_player_added_as_unpaid`, `PASSED test_internal_player_auto_marked_verified_paid`

- [ ] **Step 8: Update NewSession.tsx skill level defaults**

In `frontend/src/pages/NewSession.tsx`, change initial state:

```tsx
const [minSkill, setMinSkill] = useState<SkillLevel>('HB')  // was 'LI'
const [maxSkill, setMaxSkill] = useState<SkillLevel>('LI')  // was 'MI'
```

- [ ] **Step 9: Verify frontend builds**

```bash
cd frontend && npm run build
```

Expected: `✓ built` with no TypeScript errors.

- [ ] **Step 10: Commit**

```bash
git add supabase/migrations/006_add_cancelled_status.sql \
        backend/app/models/session.py \
        backend/app/services/session_service.py \
        backend/app/services/roster_service.py \
        backend/tests/test_roster_service.py \
        frontend/src/pages/NewSession.tsx
git commit -m "feat: empty roster on create, HB/LI defaults, internal player auto-pay"
```

---

## Task 2: Frontend types + simple fixes

**Items covered:** 4 (verify-any-player), 6 (spinner fix), 8 (422 fix), types for cancelled status

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/pages/SessionDetail.tsx`
- Modify: `frontend/src/pages/Sessions.tsx`

---

- [ ] **Step 1: Update frontend/src/types/index.ts — add 'cancelled' to SessionStatus**

```typescript
export type SessionStatus = 'internal' | 'published' | 'completed' | 'cancelled';
```

No other type changes needed for this task.

- [ ] **Step 2: Fix 422 — rename quantity → count_used in ShuttleModal + unwrap body**

In `frontend/src/pages/SessionDetail.tsx`:

1. Change the `onConfirm` prop type signature (line ~63):
```tsx
onConfirm: (usages: { batch_id: string; count_used: number }[]) => Promise<void>
```

2. In `ShuttleModal.handleSubmit` (line ~79-81), change the map:
```tsx
const usages = Object.entries(quantities)
  .filter(([, qty]) => qty > 0)
  .map(([batch_id, qty]) => ({ batch_id, count_used: qty }))  // was: quantity: qty
```

3. In `handleComplete` (line ~243-245), unwrap the body:
```tsx
async function handleComplete(usages: { batch_id: string; count_used: number }[]) {
  if (!id) return
  const updated = await api.post<Session>(`/api/v1/sessions/${id}/complete`, usages)  // was: { shuttle_usages: usages }
```

- [ ] **Step 3: Fix loading spinner — reset state in useEffect when id changes**

In `SessionDetail.tsx`, at the start of the `useEffect` (before the `async function load` declaration), add state resets:

```tsx
useEffect(() => {
  if (!id) return
  setLoading(true)    // ← ADD
  setSession(null)    // ← ADD
  setError(null)      // ← ADD
  const controller = new AbortController()
  async function load(signal: AbortSignal) {
    // ... existing code unchanged
  }
  load(controller.signal)
  return () => controller.abort()
}, [id])
```

- [ ] **Step 4: Fix verify button — show for all non-verified entries**

In `RosterRow` component (around line ~570-590), change the condition that shows the Verify button:

```tsx
// Before:
{entry.payment_status === 'pending_verification' && (
  <button onClick={() => onVerify(entry.id)} disabled={verifying}>
    Verify ✓
  </button>
)}

// After:
{entry.payment_status !== 'verified_paid' && (
  <button onClick={() => onVerify(entry.id)} disabled={verifying}
    className="rounded-lg bg-green-800 px-2 py-1 text-xs font-medium text-green-200 hover:bg-green-700 disabled:opacity-50">
    Verify ✓
  </button>
)}
```

- [ ] **Step 5: Add 'cancelled' badge to Sessions.tsx and SessionDetail.tsx**

In `Sessions.tsx`, update `STATUS_BADGE`:
```tsx
const STATUS_BADGE: Record<string, string> = {
  internal: 'bg-gray-700 text-gray-300',
  published: 'bg-green-900/60 text-green-300',
  completed: 'bg-blue-900/60 text-blue-300',
  cancelled: 'bg-red-900/60 text-red-300',   // ← ADD
}
```

In `SessionDetail.tsx`, update `STATUS_BADGE`:
```tsx
const STATUS_BADGE: Record<SessionStatus, string> = {
  internal: 'bg-gray-700 text-gray-300',
  published: 'bg-green-900/60 text-green-300',
  completed: 'bg-blue-900/60 text-blue-300',
  cancelled: 'bg-red-900/60 text-red-300',   // ← ADD
}
```

- [ ] **Step 6: Verify frontend builds**

```bash
cd frontend && npm run build
```

Expected: `✓ built` with no TypeScript errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/types/index.ts \
        frontend/src/pages/SessionDetail.tsx \
        frontend/src/pages/Sessions.tsx
git commit -m "fix: 422 complete session, loading spinner, verify-any-player, cancelled badge"
```

---

## Task 3: Cancel session backend

**Items covered:** 5 (cancel endpoint)

**Files:**
- Modify: `backend/app/models/session.py`
- Modify: `backend/app/services/session_service.py`
- Modify: `backend/app/routers/sessions.py`
- Test: `backend/tests/test_session_service.py` (new file)

**Depends on:** Task 1 (migration must include 'cancelled' status)

---

- [ ] **Step 1: Write failing test for cancel service**

Create `backend/tests/test_session_service.py`:

```python
from unittest.mock import MagicMock, patch
from uuid import uuid4
from datetime import datetime, timezone
import app.services.session_service as session_service


def _make_session_row(status: str = "published") -> dict:
    sid = str(uuid4())
    return {
        "id": sid,
        "venue_id": str(uuid4()),
        "date": "2026-06-01",
        "start_time": "20:00:00",
        "end_time": "22:00:00",
        "duration_hours": 2.0,
        "courts_booked": "3 & 4",
        "num_courts": 2,
        "min_skill_level": "HB",
        "max_skill_level": "LI",
        "pub_fee": 12.0,
        "max_pax": 12,
        "status": status,
        "telegram_message_id": None,
        "paynow_player_id": None,
        "cancellation_reason": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _make_db_client(session_row: dict):
    client = MagicMock()
    builder = MagicMock()
    builder.execute.return_value.data = [session_row]
    client.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        session_row
    ]
    client.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [
        {**session_row, "status": "cancelled"}
    ]
    return client


def test_cancel_published_session():
    """Cancelling a published session sets status to cancelled."""
    reason = "Not enough players"
    row = _make_session_row("published")
    client = _make_db_client(row)
    with patch("app.services.session_service.get_service_client", return_value=client):
        result = session_service.cancel(uuid4(), reason)
    update_payload = client.table.return_value.update.call_args[0][0]
    assert update_payload["cancellation_reason"] == reason
    assert result.status == "cancelled"


def test_cannot_cancel_completed_session():
    """Completed sessions cannot be cancelled."""
    row = _make_session_row("completed")
    client = _make_db_client(row)
    with patch("app.services.session_service.get_service_client", return_value=client):
        try:
            session_service.cancel(uuid4(), "reason")
            assert False, "Expected ValueError"
        except ValueError as e:
            assert "completed" in str(e).lower()
```

- [ ] **Step 2: Run to confirm tests fail**

```bash
cd backend && python -m pytest tests/test_session_service.py -v
```

Expected: `AttributeError: module ... has no attribute 'cancel'`

- [ ] **Step 3: Add CancelRequest model to backend/app/models/session.py**

Add at the end of `session.py`:

```python
class CancelRequest(BaseModel):
    reason: str
```

- [ ] **Step 4: Add cancel() to backend/app/services/session_service.py**

Add after the `complete()` function:

```python
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
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
cd backend && python -m pytest tests/test_session_service.py -v
```

Expected: both tests pass.

- [ ] **Step 6: Add cancel endpoint to backend/app/routers/sessions.py**

Add these imports at the top:
```python
from app.models.session import Session, SessionCreate, SessionUpdate, SessionWithRoster, CancelRequest
```

Add the endpoint after the `complete` endpoint:

```python
@router.post("/{session_id}/cancel", response_model=Session)
async def cancel_session(
    session_id: UUID,
    body: CancelRequest,
    _=Depends(require_admin),
):
    session = session_service.cancel(session_id, body.reason)
    return session
```

- [ ] **Step 7: Verify backend starts without import errors**

```bash
cd backend && python -c "from app.routers.sessions import router; print('OK')"
```

Expected: `OK`.

- [ ] **Step 8: Commit**

```bash
git add backend/app/models/session.py \
        backend/app/services/session_service.py \
        backend/app/routers/sessions.py \
        backend/tests/test_session_service.py
git commit -m "feat: cancel session endpoint with reason"
```

---

## Task 4: Frontend inline edit session

**Items covered:** 2 (edit session)

**Files:**
- Modify: `frontend/src/pages/SessionDetail.tsx`

**Depends on:** Task 1 (venue_id in SessionUpdate backend model)

---

- [ ] **Step 1: Add edit state variables to SessionDetail component**

Below the existing state declarations (around line ~167), add:

```tsx
const [editing, setEditing] = useState(false)
const [editError, setEditError] = useState<string | null>(null)
const [saving, setSaving] = useState(false)
// Single edit-form state — pre-populated when edit mode opens
const [editForm, setEditForm] = useState<Partial<Session>>({})
const [venues, setVenues] = useState<Venue[]>([])
```

Note: `venues` may already exist as a state or local variable — check and merge if needed.

- [ ] **Step 2: Add openEdit handler to pre-populate form**

Add this function after the `loadPnl` callback:

```tsx
function openEdit() {
  if (!session) return
  setEditForm(session)
  setEditing(true)
}
```

- [ ] **Step 3: Add handleSaveEdit function**

```tsx
async function handleSaveEdit() {
  if (!id) return
  setSaving(true)
  setEditError(null)
  try {
    const payload: Record<string, unknown> = {
      venue_id: editForm.venue_id || undefined,
      date: editForm.date,
      start_time: editForm.start_time,
      duration_hours: editForm.duration_hours,
      courts_booked: editForm.courts_booked,
      num_courts: editForm.num_courts,
      min_skill_level: editForm.min_skill_level,
      max_skill_level: editForm.max_skill_level,
      pub_fee: editForm.pub_fee,
      max_pax: editForm.max_pax,
      paynow_player_id: editForm.paynow_player_id || null,
    }
    const updated = await api.patch<Session>(`/api/v1/sessions/${id}`, payload)
    setSession(updated)
    setEditing(false)
  } catch (err) {
    setEditError(err instanceof Error ? err.message : 'Failed to save')
  } finally {
    setSaving(false)
  }
}
```

Ensure `api.patch` exists in `frontend/src/lib/api.ts` — if not, add it (see Step 4).

- [ ] **Step 4: Ensure api.patch exists in frontend/src/lib/api.ts**

Open `frontend/src/lib/api.ts`. If `patch` is missing, add:

```typescript
patch<T>(path: string, body: unknown): Promise<T> {
  return this.request<T>(path, { method: 'PATCH', body: JSON.stringify(body) })
},
```

(Use the same pattern as the existing `post` method.)

- [ ] **Step 5: Add the edit form panel to the JSX**

After the session header section (where the Edit button will live), add an "Edit" button next to the existing action buttons:

```tsx
{/* Show Edit button only for non-completed, non-cancelled sessions */}
{session.status !== 'completed' && session.status !== 'cancelled' && (
  <button
    onClick={openEdit}
    className="rounded-lg border border-gray-600 px-3 py-1.5 text-sm text-gray-300 hover:bg-gray-700"
  >
    ✏️ Edit
  </button>
)}
```

Add the edit form panel (rendered when `editing === true`) — place it just above the main session details card:

```tsx
{editing && (
  <div className="rounded-xl bg-gray-800 border border-brand-600 p-4 mb-4 space-y-3">
    <h2 className="font-semibold text-white">Edit Session</h2>
    {editError && (
      <p className="text-sm text-red-300 bg-red-900/40 border border-red-700 rounded-lg px-3 py-2">{editError}</p>
    )}

    <div className="grid grid-cols-2 gap-3">
      <div>
        <label className="text-xs text-gray-400">Date</label>
        <input type="date" value={editForm.date ?? ''} onChange={e => setEditForm(prev => ({...prev, date: e.target.value}))}
          className="w-full rounded-lg bg-gray-900 border border-gray-700 px-3 py-2 text-sm text-white" />
      </div>
      <div>
        <label className="text-xs text-gray-400">Start Time</label>
        <input type="time" value={(editForm.start_time ?? '').slice(0, 5)} onChange={e => setEditForm(prev => ({...prev, start_time: e.target.value + ':00'}))}
          className="w-full rounded-lg bg-gray-900 border border-gray-700 px-3 py-2 text-sm text-white" />
      </div>
      <div>
        <label className="text-xs text-gray-400">Duration (hours)</label>
        <input type="number" step="0.5" min="0.5" value={editForm.duration_hours ?? 2} onChange={e => setEditForm(prev => ({...prev, duration_hours: parseFloat(e.target.value)}))}
          className="w-full rounded-lg bg-gray-900 border border-gray-700 px-3 py-2 text-sm text-white" />
      </div>
      <div>
        <label className="text-xs text-gray-400">Venue</label>
        <select value={editForm.venue_id ?? ''} onChange={e => setEditForm(prev => ({...prev, venue_id: e.target.value}))}
          className="w-full rounded-lg bg-gray-900 border border-gray-700 px-3 py-2 text-sm text-white">
          {venues.map(v => <option key={v.id} value={v.id}>{v.name}</option>)}
        </select>
      </div>
      <div>
        <label className="text-xs text-gray-400">Courts Booked</label>
        <input type="text" value={editForm.courts_booked ?? ''} onChange={e => setEditForm(prev => ({...prev, courts_booked: e.target.value}))}
          className="w-full rounded-lg bg-gray-900 border border-gray-700 px-3 py-2 text-sm text-white" />
      </div>
      <div>
        <label className="text-xs text-gray-400">Num Courts</label>
        <input type="number" min="1" value={editForm.num_courts ?? 1} onChange={e => setEditForm(prev => ({...prev, num_courts: parseInt(e.target.value)}))}
          className="w-full rounded-lg bg-gray-900 border border-gray-700 px-3 py-2 text-sm text-white" />
      </div>
      <div>
        <label className="text-xs text-gray-400">Min Skill</label>
        <select value={editForm.min_skill_level ?? 'HB'} onChange={e => setEditForm(prev => ({...prev, min_skill_level: e.target.value as SkillLevel}))}
          className="w-full rounded-lg bg-gray-900 border border-gray-700 px-3 py-2 text-sm text-white">
          {SKILL_LEVELS.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>
      <div>
        <label className="text-xs text-gray-400">Max Skill</label>
        <select value={editForm.max_skill_level ?? 'LI'} onChange={e => setEditForm(prev => ({...prev, max_skill_level: e.target.value as SkillLevel}))}
          className="w-full rounded-lg bg-gray-900 border border-gray-700 px-3 py-2 text-sm text-white">
          {SKILL_LEVELS.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>
      <div>
        <label className="text-xs text-gray-400">Pub Fee ($)</label>
        <input type="number" step="0.5" min="0" value={editForm.pub_fee ?? 0} onChange={e => setEditForm(prev => ({...prev, pub_fee: parseFloat(e.target.value)}))}
          className="w-full rounded-lg bg-gray-900 border border-gray-700 px-3 py-2 text-sm text-white" />
      </div>
      <div>
        <label className="text-xs text-gray-400">Max Players</label>
        <input type="number" min="1" value={editForm.max_pax ?? 12} onChange={e => setEditForm(prev => ({...prev, max_pax: parseInt(e.target.value)}))}
          className="w-full rounded-lg bg-gray-900 border border-gray-700 px-3 py-2 text-sm text-white" />
      </div>
    </div>

    <div>
      <label className="text-xs text-gray-400">PayNow Player ID (UUID)</label>
      <input type="text" value={editForm.paynow_player_id ?? ''} onChange={e => setEditForm(prev => ({...prev, paynow_player_id: e.target.value || undefined}))}
        placeholder="leave blank for default"
        className="w-full rounded-lg bg-gray-900 border border-gray-700 px-3 py-2 text-sm text-white" />
    </div>

    <div className="flex gap-2 pt-1">
      <button onClick={handleSaveEdit} disabled={saving}
        className="flex-1 rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-50">
        {saving ? 'Saving…' : 'Save Changes'}
      </button>
      <button onClick={() => { setEditing(false); setEditError(null) }}
        className="rounded-lg border border-gray-600 px-4 py-2 text-sm text-gray-300 hover:bg-gray-700">
        Cancel
      </button>
    </div>
  </div>
)}
```

Make sure `SKILL_LEVELS` is imported from `../types`.

- [ ] **Step 6: Ensure venues list is loaded in the main useEffect**

The edit form needs the full venue list (not just `venueName` string). In the existing `useEffect`, the `venues` API call result is already used to set `venueName`. Ensure the full venue list is also stored:

```tsx
// In the useEffect, after setVenueName:
setVenues(venueList)   // ← store full list for edit form
```

If `venues` is already stored as a local variable only, change it to state (which was added in Step 1).

- [ ] **Step 7: Verify frontend builds**

```bash
cd frontend && npm run build
```

Expected: `✓ built` with no TypeScript errors.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/SessionDetail.tsx frontend/src/lib/api.ts
git commit -m "feat: inline edit session on detail page"
```

---

## Task 5: Bot formatter + cancel notification

**Items covered:** 7 (court label in Telegram), 5-bot (cancellation message)

**Files:**
- Modify: `backend/app/bot/message_formatter.py`
- Modify: `backend/app/bot/runner.py`
- Modify: `backend/tests/test_message_formatter.py`

**Depends on:** Task 3 (cancel service must exist)

---

- [ ] **Step 1: Update test_message_formatter.py — add cancellation + courts label test**

In `backend/tests/test_message_formatter.py`, add:

```python
def test_courts_label_shows_courts_booked_without_prefix():
    """Telegram message shows courts_booked text directly (no 'Courts:' prefix)."""
    from app.models.session import Session as S
    from datetime import date, time
    from uuid import uuid4
    from datetime import datetime, timezone
    # Build session with a specific courts_booked value for assertion
    session = _session()  # existing helper returns courts_booked="Court 1"
    text = format_session_announcement(
        session, [], {}, "Sports Hub", "Belle", "9123456"
    )
    assert f"🏟️ {session.courts_booked}" in text   # courts_booked shown directly
    assert "Courts:" not in text                    # no "Courts:" prefix


def test_format_cancellation_message():
    """Cancellation message contains date, venue, and reason."""
    from app.bot.message_formatter import format_cancellation_message
    session = _session()
    text = format_cancellation_message(session, "Sports Hub", "Not enough players")
    assert "❌" in text
    assert "Not enough players" in text
    assert "Sports Hub" in text
```

- [ ] **Step 2: Run to confirm new tests fail**

```bash
cd backend && python -m pytest tests/test_message_formatter.py::test_courts_label_shows_courts_booked_without_prefix tests/test_message_formatter.py::test_format_cancellation_message -v
```

Expected: `FAILED` (formatter still has "Courts:" prefix; `format_cancellation_message` doesn't exist).

- [ ] **Step 3: Update message_formatter.py — remove "Courts:" prefix**

In `format_session_announcement`, find:
```python
f"🏟️ Courts: {session.courts_booked}",
```
Change to:
```python
f"🏟️ {session.courts_booked}",
```

- [ ] **Step 4: Add format_cancellation_message to message_formatter.py**

```python
def format_cancellation_message(session: Session, venue_name: str, reason: str) -> str:
    """Format a cancellation notice for the LOWKEY group."""
    date_str = session.date.strftime("%a, %d %b %Y")
    time_str = f"{session.start_time.strftime('%H:%M')} - {session.end_time.strftime('%H:%M')}"
    return "\n".join([
        "❌ Session Cancelled",
        f"📅 {date_str} {time_str} · {venue_name}",
        f"Reason: {reason}",
        "Sorry for the inconvenience! 🙏",
    ])
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
cd backend && python -m pytest tests/test_message_formatter.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Add post_cancellation_message to BotRunner**

In `backend/app/bot/runner.py`, add the import at the top:
```python
from app.bot.message_formatter import (
    build_full_button,
    build_join_button,
    format_admin_summary,
    format_cancellation_message,     # ← ADD
    format_session_announcement,
)
```

Add the method to `BotRunner`:

```python
async def post_cancellation_message(self, session: Session, reason: str) -> None:
    """
    Post a cancellation notice to the LOWKEY group chat.

    Only sends if the session had a Telegram message (was published).
    """
    if session.telegram_message_id is None:
        return  # session was never published — nothing to notify

    loop = asyncio.get_running_loop()
    venue = await loop.run_in_executor(None, venue_service.get_by_id, session.venue_id)
    text = format_cancellation_message(session, venue.name, reason)

    try:
        await self._app.bot.send_message(
            chat_id=settings.telegram_lowkey_chat_id,
            text=text,
        )
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "Failed to send cancellation message for session %s", session.id
        )
```

- [ ] **Step 7: Wire bot notification into cancel router**

Now that `post_cancellation_message` is defined, update `backend/app/routers/sessions.py` to add the background task:

```python
@router.post("/{session_id}/cancel", response_model=Session)
async def cancel_session(
    session_id: UUID,
    body: CancelRequest,
    _=Depends(require_admin),
):
    session = session_service.cancel(session_id, body.reason)
    asyncio.create_task(bot_runner.post_cancellation_message(session, body.reason))
    return session
```

- [ ] **Step 8: Verify the cancel endpoint resolves correctly**

```bash
cd backend && python -c "from app.routers.sessions import router; print('OK')"
```

Expected: `OK` (now that `post_cancellation_message` is defined).

- [ ] **Step 9: Commit**

```bash
git add backend/app/bot/message_formatter.py \
        backend/app/bot/runner.py \
        backend/app/routers/sessions.py \
        backend/tests/test_message_formatter.py
git commit -m "feat: court label in Telegram, cancellation bot message"
```

---

## Task 6: Frontend cancel UI

**Items covered:** 5-frontend (cancel modal)

**Files:**
- Modify: `frontend/src/pages/SessionDetail.tsx`

**Depends on:** Task 2 (cancelled badge exists), Task 3 (cancel endpoint exists)

---

- [ ] **Step 1: Add cancel state variables to SessionDetail**

Add below existing state:

```tsx
const [showCancelModal, setShowCancelModal] = useState(false)
const [cancelReason, setCancelReason] = useState('')
const [cancelling, setCancelling] = useState(false)
const [cancelError, setCancelError] = useState<string | null>(null)
```

- [ ] **Step 2: Add handleCancel function**

```tsx
async function handleCancel() {
  if (!id || !cancelReason.trim()) return
  setCancelling(true)
  setCancelError(null)
  try {
    const updated = await api.post<Session>(`/api/v1/sessions/${id}/cancel`, { reason: cancelReason })
    setSession(updated)
    setShowCancelModal(false)
    setCancelReason('')
  } catch (err) {
    setCancelError(err instanceof Error ? err.message : 'Failed to cancel session')
  } finally {
    setCancelling(false)
  }
}
```

- [ ] **Step 3: Add Cancel button in action buttons section**

In the session action buttons area (near the "Publish" and "Complete" buttons), add:

```tsx
{(session.status === 'internal' || session.status === 'published') && (
  <button
    onClick={() => setShowCancelModal(true)}
    className="rounded-lg border border-red-700 px-3 py-1.5 text-sm font-medium text-red-300 hover:bg-red-900/30"
  >
    🚫 Cancel Session
  </button>
)}
```

- [ ] **Step 4: Add cancel modal JSX**

Add at the bottom of the return statement (before closing `</div>`):

```tsx
{showCancelModal && (
  <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/70 px-4 pb-4">
    <div className="w-full max-w-md rounded-2xl bg-gray-900 border border-gray-700 p-5">
      <h2 className="text-lg font-bold text-white mb-1">Cancel Session</h2>
      <p className="text-sm text-gray-400 mb-4">
        This will notify all players via Telegram. Please provide a reason.
      </p>
      {cancelError && (
        <p className="rounded-lg bg-red-900/50 border border-red-700 px-3 py-2 text-sm text-red-300 mb-3">
          {cancelError}
        </p>
      )}
      <textarea
        value={cancelReason}
        onChange={e => setCancelReason(e.target.value)}
        rows={3}
        placeholder="e.g. Not enough players signed up"
        className="w-full rounded-lg bg-gray-800 border border-gray-700 px-3 py-2 text-sm text-white resize-none mb-4"
      />
      <div className="flex gap-2">
        <button
          onClick={handleCancel}
          disabled={cancelling || !cancelReason.trim()}
          className="flex-1 rounded-lg bg-red-700 px-4 py-2 text-sm font-semibold text-white hover:bg-red-600 disabled:opacity-50"
        >
          {cancelling ? 'Cancelling…' : 'Confirm Cancel'}
        </button>
        <button
          onClick={() => { setShowCancelModal(false); setCancelError(null) }}
          className="rounded-lg border border-gray-600 px-4 py-2 text-sm text-gray-300 hover:bg-gray-700"
        >
          Back
        </button>
      </div>
    </div>
  </div>
)}
```

- [ ] **Step 5: Verify frontend builds**

```bash
cd frontend && npm run build
```

Expected: `✓ built` with no TypeScript errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/SessionDetail.tsx
git commit -m "feat: cancel session UI with reason modal"
```

---

## Self-review

**Spec coverage check:**
- ✅ Item 1 (empty roster): Task 1 Step 5
- ✅ Item 2 (edit session): Task 4
- ✅ Item 3 (skill defaults): Task 1 Step 4 + Step 8
- ✅ Item 4 (verify any player): Task 2 Step 4
- ✅ Item 5 (cancel): Task 3 + Task 5 + Task 6
- ✅ Item 6 (loading spinner): Task 2 Step 3
- ✅ Item 7 (court label): Task 5 Step 3
- ✅ Item 8 (422 fix): Task 2 Step 2
- ✅ Item 9 (internal auto-pay): Task 1 Step 6
- ✅ DB migration (cancelled + cancellation_reason + payment_status): Task 1 Step 3

**Review fixes applied:**
- `settings.telegram_lowkey_chat_id` used (not `lowkey_group_chat_id`)
- Test helper `_session()` used (not `_make_session()`); courts assertion uses `session.courts_booked` dynamically
- `cancellation_reason` stored in DB + in Session model
- `cancel()` stores both `status` and `cancellation_reason` in single update
- Router passes `Session` object to bot (no extra DB fetch in `post_cancellation_message`)
- Bot logs exceptions on Telegram failure instead of silently swallowing
- `session_service.update()` uses `exclude_unset=True` (allows clearing nullable fields)
- `__import__` anti-pattern removed; normal `from unittest.mock import patch` used

**Type consistency:**
- `CancelRequest` defined in Task 3, used in Task 3 router and Task 6 frontend — consistent.
- `Session.cancellation_reason` added in Task 1 Step 4, used in Task 3 test — consistent.
- `SkillLevel` / `SKILL_LEVELS` imported from `../types` in Task 4 edit form.
- `api.patch` defined in Task 4 Step 4 — used in Task 4 Step 3.
- `format_cancellation_message` defined in Task 5 Step 4, imported in Task 5 Step 6 — consistent.
- `post_cancellation_message(session, reason)` signature matches router call in Task 5 Step 7.
