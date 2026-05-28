# Bot & Fund Features Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 5 new features: player withdraw via bot, /help command, P&L fund balance ledger, recruit-players message generator, and auto-delete session message on completion.

**Architecture:** All bot features follow the established pattern: pure formatter functions in `message_formatter.py`, async send/notify methods in `runner.py`, and callback/command handlers registered in `handlers.py`. The fund ledger uses a new `fund_entries` Supabase table with a `fund_service` + `fund` router; shuttle batch creation automatically inserts a negative fund entry for the purchase cost. Frontend wires into the new endpoints on the PnL and SessionDetail pages.

**Tech Stack:** FastAPI, python-telegram-bot 20.x, Pydantic v2, Supabase-py, React + Vite + Tailwind CSS.

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `supabase/migrations/007_fund_entries.sql` | **Create** | `fund_entries` table |
| `backend/app/models/fund.py` | **Create** | `FundEntry`, `FundEntryCreate`, `FundBalance` models |
| `backend/app/services/fund_service.py` | **Create** | `get_entries()`, `add_entry()`, `get_balance()` |
| `backend/app/routers/fund.py` | **Create** | `GET /fund/balance`, `GET /fund/entries`, `POST /fund/entries` |
| `backend/app/main.py` | **Modify** | Include fund router |
| `backend/app/services/roster_service.py` | **Modify** | Add `remove_player(session_id, telegram_user_id)` |
| `backend/app/services/shuttle_service.py` | **Modify** | Auto-deduct fund in `create()` |
| `backend/app/bot/message_formatter.py` | **Modify** | Add `format_withdraw_notification()`, `format_help_text()`, `format_recruit_message()`, `build_join_leave_buttons()` |
| `backend/app/bot/handlers.py` | **Modify** | Add `handle_withdraw_callback()`, `handle_help_command()` |
| `backend/app/bot/runner.py` | **Modify** | Add `post_withdraw_notification()`, `delete_session_message()`, `post_recruit_message()`; update `build()` to register new handlers; update `edit_session_message()` to use `build_join_leave_buttons` |
| `backend/app/routers/sessions.py` | **Modify** | Add `POST /{id}/recruit`; wire `delete_session_message` in complete endpoint |
| `frontend/src/types/index.ts` | **Modify** | Add `FundEntry`, `FundBalance` types |
| `frontend/src/pages/PnL.tsx` | **Modify** | Add fund balance section + add-entry form |
| `frontend/src/pages/SessionDetail.tsx` | **Modify** | Add "Generate Recruit Message" button + copy modal |
| `backend/tests/test_fund_service.py` | **Create** | Unit tests for fund_service |
| `backend/tests/test_roster_withdraw.py` | **Create** | Unit tests for `remove_player()` |
| `backend/tests/test_bot_new_formatters.py` | **Create** | Behavior tests for new formatter functions |
| `backend/tests/test_e2e_new_features.py` | **Create** | E2E integration test |

---

## Wave 1 — Foundation (Tasks 1–3, run in parallel)

### Task 1: DB Migration + Fund Models + Fund Service + Fund Router

**Files:**
- Create: `supabase/migrations/007_fund_entries.sql`
- Create: `backend/app/models/fund.py`
- Create: `backend/app/services/fund_service.py`
- Create: `backend/app/routers/fund.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_fund_service.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_fund_service.py
from unittest.mock import MagicMock, patch
from uuid import uuid4
from datetime import datetime, timezone

import pytest

_NOW = datetime.now(timezone.utc).isoformat()
_ENTRY_ROW = {"id": str(uuid4()), "description": "Opening balance", "amount": 150.0, "created_at": _NOW}


def _make_client(rows=None):
    rows = rows if rows is not None else []
    client = MagicMock()
    client.table.return_value.select.return_value.order.return_value.execute.return_value.data = rows
    client.table.return_value.insert.return_value.execute.return_value.data = rows[:1] if rows else [_ENTRY_ROW]
    return client


def test_get_entries_returns_fund_entries():
    with patch("app.services.fund_service.get_service_client", return_value=_make_client([_ENTRY_ROW])):
        import app.services.fund_service as fund_service
        entries = fund_service.get_entries()
    assert len(entries) == 1
    assert entries[0].amount == 150.0


def test_add_entry_inserts_row():
    inserted = {"id": str(uuid4()), "description": "Opening balance", "amount": 200.0, "created_at": _NOW}
    client = _make_client([inserted])
    client.table.return_value.insert.return_value.execute.return_value.data = [inserted]
    with patch("app.services.fund_service.get_service_client", return_value=client):
        import app.services.fund_service as fund_service
        from app.models.fund import FundEntryCreate
        entry = fund_service.add_entry(FundEntryCreate(description="Opening balance", amount=200.0))
    assert entry.amount == 200.0
    assert entry.description == "Opening balance"


def test_get_balance_sums_entries():
    rows = [
        {"id": str(uuid4()), "description": "Opening", "amount": 150.0, "created_at": _NOW},
        {"id": str(uuid4()), "description": "Shuttles", "amount": -40.0, "created_at": _NOW},
    ]
    with patch("app.services.fund_service.get_service_client", return_value=_make_client(rows)):
        import app.services.fund_service as fund_service
        balance = fund_service.get_balance()
    assert balance.entries_total == pytest.approx(110.0)
    assert len(balance.entries) == 2
```

- [ ] **Step 2: Create the DB migration**

```sql
-- supabase/migrations/007_fund_entries.sql
-- Fund ledger: tracks opening balance and shuttle purchase costs.
-- Positive amount = income / deposit; negative = expense.

CREATE TABLE IF NOT EXISTS fund_entries (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    description TEXT        NOT NULL,
    amount      NUMERIC     NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE fund_entries ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role full access" ON fund_entries
    FOR ALL USING (true) WITH CHECK (true);
```

- [ ] **Step 4: Create the fund models**

```python
# backend/app/models/fund.py
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class FundEntry(BaseModel):
    id: UUID
    description: str
    amount: float  # positive = deposit/income; negative = expense
    created_at: datetime


class FundEntryCreate(BaseModel):
    description: str
    amount: float


class FundBalance(BaseModel):
    entries: list[FundEntry]
    entries_total: float
```

- [ ] **Step 5: Create the fund service**

```python
# backend/app/services/fund_service.py
from app.db.client import get_service_client
from app.models.fund import FundBalance, FundEntry, FundEntryCreate


def get_entries() -> list[FundEntry]:
    client = get_service_client()
    result = client.table("fund_entries").select("*").order("created_at").execute()
    return [FundEntry(**row) for row in result.data]


def add_entry(data: FundEntryCreate) -> FundEntry:
    client = get_service_client()
    result = client.table("fund_entries").insert(data.model_dump(mode="json")).execute()
    return FundEntry(**result.data[0])


def get_balance() -> FundBalance:
    entries = get_entries()
    total = sum(e.amount for e in entries)
    return FundBalance(entries=entries, entries_total=round(total, 2))
```

- [ ] **Step 6: Create the fund router**

```python
# backend/app/routers/fund.py
from fastapi import APIRouter, Depends

from app.dependencies import require_admin
from app.models.fund import FundBalance, FundEntry, FundEntryCreate
import app.services.fund_service as fund_service

router = APIRouter(prefix="/fund")


@router.get("/balance", response_model=FundBalance)
async def get_fund_balance(_=Depends(require_admin)):
    return fund_service.get_balance()


@router.post("/entries", response_model=FundEntry, status_code=201)
async def create_fund_entry(data: FundEntryCreate, _=Depends(require_admin)):
    return fund_service.add_entry(data)
```

- [ ] **Step 7: Register fund router in main.py**

In `backend/app/main.py`, add to the import line:
```python
from app.routers import sessions, roster, players, inventory, pnl, venues, court_slots, fund
```
And add after the existing `app.include_router` calls:
```python
app.include_router(fund.router, prefix="/api/v1", tags=["fund"])
```

- [ ] **Step 8: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_fund_service.py -v
```
Expected: PASS (3 tests)

- [ ] **Step 9: Commit**

```bash
git add supabase/migrations/007_fund_entries.sql backend/app/models/fund.py backend/app/services/fund_service.py backend/app/routers/fund.py backend/app/main.py backend/tests/test_fund_service.py
git commit -m "feat: add fund ledger (DB migration, service, router)"
```

---

### Task 2: roster_service.remove_player()

**Files:**
- Modify: `backend/app/services/roster_service.py`
- Test: `backend/tests/test_roster_withdraw.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_roster_withdraw.py
from unittest.mock import MagicMock, call, patch
from uuid import uuid4
from datetime import datetime, timezone

import pytest

from app.models.roster import RosterEntry

_NOW = datetime.now(timezone.utc).isoformat()
_SESSION_ID = uuid4()
_PLAYER_ID = uuid4()
_ENTRY_ID = uuid4()
_TELEGRAM_ID = 99999


def _roster_row(player_id=_PLAYER_ID, is_waitlisted=False, payment_status="unpaid"):
    return {
        "id": str(_ENTRY_ID),
        "session_id": str(_SESSION_ID),
        "player_id": str(player_id),
        "guest_name": None,
        "player_type": "registered",
        "payment_status": payment_status,
        "is_waitlisted": is_waitlisted,
        "position": 1,
        "joined_at": _NOW,
        "created_at": _NOW,
    }


def _player_row():
    return {
        "id": str(_PLAYER_ID),
        "name": "Alice",
        "telegram_id": _TELEGRAM_ID,
        "is_internal": False,
        "is_admin": False,
        "phone": None,
        "skill_level": "HB",
        "notes": None,
        "created_at": _NOW,
    }


def test_remove_player_deletes_roster_entry():
    """remove_player finds the player's entry and deletes it via remove_entry."""
    import app.services.roster_service as roster_service

    with (
        patch("app.services.roster_service.player_service.get_by_telegram_id") as mock_player,
        patch("app.services.roster_service.get_service_client") as mock_client_fn,
        patch("app.services.roster_service.remove_entry") as mock_remove,
    ):
        from app.models.player import Player
        mock_player.return_value = Player(**_player_row())
        client = MagicMock()
        client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
            {"id": str(_ENTRY_ID)}
        ]
        mock_client_fn.return_value = client
        removed_entry = RosterEntry(**_roster_row())
        mock_remove.return_value = removed_entry

        result = roster_service.remove_player(_SESSION_ID, _TELEGRAM_ID)

    assert result.id == removed_entry.id
    assert result.session_id == removed_entry.session_id


def test_remove_player_raises_if_not_on_roster():
    """remove_player raises ValueError when player has no roster entry for the session."""
    import app.services.roster_service as roster_service

    with (
        patch("app.services.roster_service.player_service.get_by_telegram_id") as mock_player,
        patch("app.services.roster_service.get_service_client") as mock_client_fn,
    ):
        from app.models.player import Player
        mock_player.return_value = Player(**_player_row())
        client = MagicMock()
        client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
        mock_client_fn.return_value = client

        with pytest.raises(ValueError, match="not on this session"):
            roster_service.remove_player(_SESSION_ID, _TELEGRAM_ID)


def test_remove_player_raises_if_player_unknown():
    """remove_player raises ValueError when telegram_id not found."""
    import app.services.roster_service as roster_service

    with patch("app.services.roster_service.player_service.get_by_telegram_id", return_value=None):
        with pytest.raises(ValueError, match="Player not found"):
            roster_service.remove_player(_SESSION_ID, _TELEGRAM_ID)
```

- [ ] **Step 2: Add remove_player to roster_service.py**

Add the following function at the bottom of `backend/app/services/roster_service.py` (after `verify_payment`):

```python
def remove_player(session_id: UUID, telegram_user_id: int) -> RosterEntry:
    """Remove a registered player from the roster by their Telegram ID.

    Raises ValueError if the player or their roster entry is not found.
    Returns the deleted RosterEntry (so callers can inspect payment_status).
    """
    player = player_service.get_by_telegram_id(telegram_user_id)
    if player is None:
        raise ValueError("Player not found")

    client = get_service_client()
    result = (
        client.table("roster_entries")
        .select("id")
        .eq("session_id", str(session_id))
        .eq("player_id", str(player.id))
        .execute()
    )
    if not result.data:
        raise ValueError("You are not on this session's roster.")

    entry_id = UUID(result.data[0]["id"])
    removed = remove_entry(entry_id)
    if removed is None:
        raise ValueError("Failed to remove roster entry")
    return removed
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_roster_withdraw.py -v
```
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/roster_service.py backend/tests/test_roster_withdraw.py
git commit -m "feat: add roster_service.remove_player() for bot withdraw"
```

---

### Task 3: New Message Formatter Functions

**Files:**
- Modify: `backend/app/bot/message_formatter.py`
- Test: `backend/tests/test_bot_new_formatters.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_bot_new_formatters.py
"""Behavior tests for new pure formatter functions — no mocks needed."""
from datetime import date, time, datetime, timezone
from uuid import uuid4

import pytest

from app.bot.message_formatter import (
    build_join_leave_buttons,
    format_help_text,
    format_recruit_message,
    format_withdraw_notification,
)
from app.models.session import Session

_NOW = datetime.now(timezone.utc)
_SESSION_ID = uuid4()
_VENUE_ID = uuid4()


def _session(max_pax=12, num_courts=2) -> Session:
    return Session(
        id=_SESSION_ID,
        venue_id=_VENUE_ID,
        date=date(2026, 5, 31),
        start_time=time(20, 0),
        end_time=time(22, 0),
        duration_hours=2.0,
        courts_booked="Court 1 & 2",
        num_courts=num_courts,
        min_skill_level="HB",
        max_skill_level="LI",
        pub_fee=12.0,
        max_pax=max_pax,
        status="published",
        created_at=_NOW,
    )


def test_format_recruit_message_content():
    """recruit message includes slots, venue, fee, courts, shuttle line, and sign-off."""
    msg = format_recruit_message(_session(), slots_left=3, venue_name="Fengshan CC")
    assert "[3 slots left]" in msg
    assert "RSL Ultimate shuttles provided" in msg
    assert "Fengshan CC" in msg
    assert "$12" in msg
    assert "PM if interested" in msg


def test_format_recruit_message_slot_singularity():
    """'slot' (not 'slots') when only 1 slot remains."""
    msg = format_recruit_message(_session(), slots_left=1, venue_name="Fengshan CC")
    assert "[1 slot left]" in msg


def test_format_recruit_message_courts_label():
    """Court count label is singular/plural correctly."""
    assert "1 court" in format_recruit_message(_session(num_courts=1), slots_left=2, venue_name="V")
    assert "2 courts" in format_recruit_message(_session(num_courts=2), slots_left=2, venue_name="V")


def test_format_withdraw_notification_paid_includes_return_warning():
    msg = format_withdraw_notification("Bob", _session(), "Fengshan CC", was_paid=True)
    assert "Bob" in msg
    assert "return" in msg.lower()


def test_format_withdraw_notification_unpaid_no_return_warning():
    msg = format_withdraw_notification("Bob", _session(), "Fengshan CC", was_paid=False)
    assert "Bob" in msg
    assert "return" not in msg.lower()


def test_format_help_text_covers_join_leave_pay():
    msg = format_help_text()
    assert "Join" in msg
    assert "Leave" in msg
    assert "PayNow" in msg


def test_build_join_leave_buttons_not_full_has_join_and_leave():
    kb = build_join_leave_buttons(str(_SESSION_ID), is_full=False)
    buttons = [btn.text for row in kb.inline_keyboard for btn in row]
    assert any("Join" in b for b in buttons)
    assert any("Leave" in b for b in buttons)


def test_build_join_leave_buttons_full_has_full_and_leave():
    kb = build_join_leave_buttons(str(_SESSION_ID), is_full=True)
    buttons = [btn.text for row in kb.inline_keyboard for btn in row]
    assert any("Full" in b for b in buttons)
    assert any("Leave" in b for b in buttons)
```

- [ ] **Step 2: Add new functions to message_formatter.py**

Append the following to `backend/app/bot/message_formatter.py`. Also add `build_join_leave_buttons` and **delete** the now-unused `build_join_button` and `build_full_button` functions. Update `backend/tests/test_message_formatter.py` to remove the import of the deleted functions and replace their test with:

```python
from app.bot.message_formatter import build_join_leave_buttons

def test_build_join_leave_buttons_not_full():
    kb = build_join_leave_buttons(str(_SESSION_ID), is_full=False)
    texts = [btn.text for row in kb.inline_keyboard for btn in row]
    assert any("Join" in t for t in texts)
    assert any("Leave" in t for t in texts)

def test_build_join_leave_buttons_full():
    kb = build_join_leave_buttons(str(_SESSION_ID), is_full=True)
    texts = [btn.text for row in kb.inline_keyboard for btn in row]
    assert any("Full" in t for t in texts)
    assert any("Leave" in t for t in texts)
```

```python
def format_withdraw_notification(
    player_name: str,
    session: Session,
    venue_name: str,
    was_paid: bool,
) -> str:
    """Format an admin-group notification when a player withdraws."""
    date_str = session.date.strftime("%a, %d %b %Y")
    time_str = f"{session.start_time.strftime('%H:%M')} – {session.end_time.strftime('%H:%M')}"
    pay_line = "⚠️ They had PAID — please return their money. 💸" if was_paid else "They had not paid."
    return "\n".join([
        f"🚪 {player_name} has withdrawn from the session.",
        f"📅 {date_str} {time_str} · {venue_name}",
        pay_line,
    ])


def format_help_text() -> str:
    """Player-facing /help guide."""
    return "\n".join([
        "🏸 Badminton Bot — Help",
        "",
        "▶️ To join a game:",
        "  Press [Join ✋] on any session post in the group.",
        "",
        "🚪 To leave a game:",
        "  Press [Leave 🚪] on the same session post.",
        "",
        "💳 To pay:",
        "  PayNow to the details shown in the session post.",
        "  Send your payment screenshot to an admin.",
        "  Admin will mark you as ✅ paid once confirmed.",
        "",
        "❓ Need help? Message an admin directly.",
    ])


def format_recruit_message(session: Session, slots_left: int, venue_name: str) -> str:
    """Format a player-recruitment post for the admin group."""
    date_str = session.date.strftime("%d %b %Y, %a")
    start_str = session.start_time.strftime("%I:%M %p").lstrip("0")
    end_str = session.end_time.strftime("%I:%M %p").lstrip("0")
    # _skill_range_label returns "🎯 Level: HB – LI" — use raw values to avoid double prefix
    if session.min_skill_level == session.max_skill_level:
        skill_str = session.min_skill_level
    else:
        skill_str = f"{session.min_skill_level} – {session.max_skill_level}"
    slot_label = f"[{slots_left} slot{'s' if slots_left != 1 else ''} left]"
    court_label = f"{session.num_courts} court{'s' if session.num_courts != 1 else ''}"
    return "\n".join([
        "Looking for friendly players to join the following game:",
        "",
        slot_label,
        f"Date: {date_str}",
        f"Time: {start_str} – {end_str}",
        f"Venue: {venue_name}",
        f"Level: {skill_str}",
        f"Cost: ${session.pub_fee:.0f} per pax",
        f"Max {session.max_pax} pax, ({court_label})",
        "RSL Ultimate shuttles provided",
        "",
        "PM if interested, thank you!",
    ])


def build_join_leave_buttons(session_id: str, is_full: bool) -> InlineKeyboardMarkup:
    """Build inline keyboard with Join (or Full) and Leave buttons."""
    join_btn = (
        InlineKeyboardButton("Full 🔒", callback_data="full")
        if is_full
        else InlineKeyboardButton("Join ✋", callback_data=f"join:{session_id}")
    )
    leave_btn = InlineKeyboardButton("Leave 🚪", callback_data=f"leave:{session_id}")
    return InlineKeyboardMarkup([[join_btn, leave_btn]])
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_bot_new_formatters.py -v
```
Expected: PASS (11 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/bot/message_formatter.py backend/tests/test_bot_new_formatters.py
git commit -m "feat: add withdraw/help/recruit formatters and join+leave button builder"
```

---

## Wave 2 — Bot Handlers & Runner (Tasks 4 then 5, sequential — Task 5 imports symbols added by Task 4)

### Task 4: Bot Handlers — handle_withdraw_callback + handle_help_command

**Files:**
- Modify: `backend/app/bot/handlers.py`

> **Note:** This task depends on Task 2 (`roster_service.remove_player`) and Task 3 (`format_help_text`, `format_withdraw_notification`). Ensure both are merged before starting.

- [ ] **Step 1: Add imports at the top of handlers.py**

At the top of `backend/app/bot/handlers.py`, ensure the following imports are present (add if missing):
```python
from app.bot.message_formatter import format_withdraw_notification, format_help_text
import app.services.session_service as session_service
```

- [ ] **Step 2: Add handle_withdraw_callback**

Add the following function to `backend/app/bot/handlers.py`, after `handle_join_callback`:

```python
async def handle_withdraw_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handler for the "Leave 🚪" inline button press.

    Flow:
    1. Parse session_id from callback_data ("leave:{session_id}").
    2. Remove the player from the roster via roster_service.remove_player().
    3. Edit the session message to reflect updated list.
    4. Notify the admin group that this player withdrew.
    """
    query = update.callback_query
    telegram_user_id = query.from_user.id
    session_id = UUID(query.data.split(":", 1)[1])

    loop = asyncio.get_running_loop()

    # Guard: only allow withdrawals from published sessions
    session = await loop.run_in_executor(None, session_service.get_by_id, session_id)
    if session.status != "published":
        await query.answer("This session is no longer open for changes.", show_alert=True)
        return

    try:
        removed = await loop.run_in_executor(
            None, roster_service.remove_player, session_id, telegram_user_id
        )
    except ValueError as exc:
        await query.answer(str(exc), show_alert=True)
        return

    player = await loop.run_in_executor(
        None, player_service.get_by_telegram_id, telegram_user_id
    )
    player_name = player.name if player else "Unknown"

    await query.answer(f"You've left the session, {player_name}. See you next time! 👋", show_alert=True)

    from app.bot.runner import bot_runner

    await bot_runner.edit_session_message(session_id)
    await bot_runner.post_withdraw_notification(removed, player_name, session_id)
```

- [ ] **Step 3: Add handle_help_command**

Add the following function to `backend/app/bot/handlers.py`, after `handle_withdraw_callback`:

```python
async def handle_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Respond to /help with a player-facing usage guide."""
    await update.message.reply_text(format_help_text())
```

- [ ] **Step 4: Verify the module imports cleanly**

```bash
cd backend && python -c "from app.bot.handlers import handle_withdraw_callback, handle_help_command; print('OK')"
```
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/app/bot/handlers.py
git commit -m "feat: add handle_withdraw_callback and handle_help_command bot handlers"
```

---

### Task 5: BotRunner — post_withdraw_notification, delete_session_message, post_recruit_message + handler registration

**Files:**
- Modify: `backend/app/bot/runner.py`

> **Note:** This task depends on Task 3 (formatter functions) AND Task 4 (handler symbols). Ensure BOTH are merged before starting.

- [ ] **Step 1: Update imports in runner.py**

At the top of `backend/app/bot/runner.py`, update the import from `handlers` to include the new handlers:
```python
from app.bot.handlers import (
    handle_join_callback,
    handle_name_message,
    handle_start,
    handle_withdraw_callback,
    handle_help_command,
    periodic_cleanup,
)
```

Update the import from `message_formatter` to include the new functions:
```python
from app.bot.message_formatter import (
    build_join_leave_buttons,
    format_admin_summary,
    format_cancellation_message,
    format_recruit_message,
    format_session_announcement,
    format_withdraw_notification,
)
```

Remove `build_full_button` and `build_join_button` from the import (they are replaced by `build_join_leave_buttons`). Note: these functions are kept in `message_formatter.py` so existing tests continue to pass — only the `runner.py` import is updated.

- [ ] **Step 2: Register new handlers in build()**

In `BotRunner.build()`, add after the existing `CallbackQueryHandler` registration:
```python
self._app.add_handler(
    CallbackQueryHandler(handle_withdraw_callback, pattern=r"^leave:")
)
self._app.add_handler(CommandHandler("help", handle_help_command))
```

- [ ] **Step 3a: Update edit_session_message() to use build_join_leave_buttons**

In `BotRunner.edit_session_message()`, replace:
```python
        is_full = active_count >= session.max_pax
        keyboard: InlineKeyboardMarkup = (
            build_full_button() if is_full else build_join_button(str(session_id))
        )
```
With:
```python
        is_full = active_count >= session.max_pax
        keyboard = build_join_leave_buttons(str(session_id), is_full=is_full)
```

- [ ] **Step 3b: Update post_session_announcement() to use build_join_leave_buttons**

In `BotRunner.post_session_announcement()`, find the line `keyboard = build_join_button(str(session.id))` and replace with:
```python
        keyboard = build_join_leave_buttons(str(session.id), is_full=False)
```

Both `build_join_button` and `build_full_button` were deleted in Task 3 — they are no longer in `message_formatter.py` or imported here.

- [ ] **Step 4: Add post_withdraw_notification method**

Add the following method to `BotRunner`, after `post_cancellation_message`:

```python
    async def post_withdraw_notification(
        self, entry: RosterEntry, player_name: str, session_id: UUID
    ) -> None:
        """Notify the admin group when a player withdraws."""
        loop = asyncio.get_running_loop()
        session = await loop.run_in_executor(None, session_service.get_by_id, session_id)
        venue = await loop.run_in_executor(None, venue_service.get_by_id, session.venue_id)
        was_paid = entry.payment_status == "verified_paid"
        text = format_withdraw_notification(player_name, session, venue.name, was_paid)
        try:
            await self._app.bot.send_message(
                chat_id=settings.telegram_admin_chat_id,
                text=text,
            )
        except Exception:
            logging.getLogger(__name__).exception(
                "Failed to send withdraw notification for session %s", session_id
            )
```

- [ ] **Step 5: Add delete_session_message method**

Add after `post_withdraw_notification`:

```python
    async def delete_session_message(self, session: Session) -> None:
        """Delete the LOWKEY group message when a session is completed."""
        if session.telegram_message_id is None:
            return
        try:
            await self._app.bot.delete_message(
                chat_id=settings.telegram_lowkey_chat_id,
                message_id=session.telegram_message_id,
            )
        except Exception:
            logging.getLogger(__name__).exception(
                "Failed to delete session message %s", session.id
            )
```

- [ ] **Step 6: Add post_recruit_message method**

Add after `delete_session_message`:

```python
    async def post_recruit_message(self, message: str) -> None:
        """Send a recruitment message to the admin group."""
        try:
            await self._app.bot.send_message(
                chat_id=settings.telegram_admin_chat_id,
                text=message,
            )
        except Exception:
            logging.getLogger(__name__).exception("Failed to post recruit message")
```

- [ ] **Step 7: Verify the module imports and bot starts cleanly**

```bash
cd backend && python -c "from app.bot.runner import bot_runner; bot_runner.build(); print('OK')"
```
Expected: `OK` (no errors; bot won't actually connect without a valid token, but imports succeed)

- [ ] **Step 8: Commit**

```bash
git add backend/app/bot/runner.py
git commit -m "feat: add withdraw notification, delete message, recruit post to BotRunner; register /help and leave: handlers"
```

---

## Wave 3 — Endpoints, Shuttle Auto-Deduct, Frontend (Tasks 6–9, run in parallel)

### Task 6: Sessions Router — POST /recruit + complete endpoint wire-up

**Files:**
- Modify: `backend/app/routers/sessions.py`

> **Note:** This task depends on Task 5 (runner methods). Ensure Task 5 is merged before starting.

- [ ] **Step 1: Update imports in sessions.py**

At the top of `backend/app/routers/sessions.py`, ensure these imports are present (add missing ones):
```python
import app.services.venue_service as venue_service
import app.services.roster_service as roster_service
from app.bot.message_formatter import format_recruit_message
```

- [ ] **Step 2: Wire delete_session_message into the complete endpoint**

Replace the existing `complete_session` endpoint:
```python
@router.post("/{session_id}/complete", response_model=SessionWithRoster)
async def complete_session(
    session_id: UUID,
    shuttle_usages: list[ShuttleUsageCreate] = Body(default=[]),
    _=Depends(require_admin),
):
    session_before = session_service.get_by_id(session_id)
    result = session_service.complete(session_id, shuttle_usages)
    asyncio.create_task(bot_runner.delete_session_message(session_before))
    return result
```

- [ ] **Step 3: Add POST /{session_id}/recruit endpoint**

Add the following after the `cancel_session` endpoint:
```python
@router.post("/{session_id}/recruit", response_model=dict)
async def recruit_players(session_id: UUID, _=Depends(require_admin)):
    """Generate a recruit message, send it to the admin group, and return the text."""
    session = session_service.get_by_id(session_id)
    venue = venue_service.get_by_id(session.venue_id)
    roster = roster_service.get_session_roster(session_id)
    active_count = sum(1 for e in roster if not e.is_waitlisted)
    slots_left = max(0, session.max_pax - active_count)
    message = format_recruit_message(session, slots_left, venue.name)
    asyncio.create_task(bot_runner.post_recruit_message(message))
    return {"message": message}
```

- [ ] **Step 4: Verify the router imports cleanly**

```bash
cd backend && python -c "from app.routers.sessions import router; print('OK')"
```
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/sessions.py
git commit -m "feat: wire bot.delete_session_message on complete; add POST /sessions/{id}/recruit"
```

---

### Task 7: Shuttle Service — Fund Auto-Deduct on Batch Create

**Files:**
- Modify: `backend/app/services/shuttle_service.py`

> **Note:** This task depends on Task 1 (fund_service). Ensure Task 1 is merged before starting.

- [ ] **Step 1: Add fund_service import**

At the top of `backend/app/services/shuttle_service.py`, add:
```python
import math

import app.services.fund_service as fund_service
from app.models.fund import FundEntryCreate
```

- [ ] **Step 2: Update create() to auto-deduct from fund**

Replace the existing `create()` function:
```python
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
        fund_service.add_entry(FundEntryCreate(
            description=f"Shuttle batch: {batch.batch_name} ({batch.brand})",
            amount=-purchase_cost,
        ))

    return batch
```

- [ ] **Step 3: Verify the module imports cleanly**

```bash
cd backend && python -c "from app.services.shuttle_service import create; print('OK')"
```
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/shuttle_service.py
git commit -m "feat: auto-deduct fund on shuttle batch creation"
```

---

### Task 8: Frontend — Fund Balance Section in PnL Page

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/pages/PnL.tsx`

> **Note:** This task depends on Task 1 (fund router must exist at `/api/v1/fund/balance`). Ensure Task 1 is deployed/running before testing.

- [ ] **Step 1: Add FundEntry and FundBalance types**

Append to `frontend/src/types/index.ts`:
```typescript
export interface FundEntry {
  id: string
  description: string
  amount: number  // positive = income; negative = expense
  created_at: string
}

export interface FundBalance {
  entries: FundEntry[]
  entries_total: number
}
```

- [ ] **Step 2: Add fund state and fetch to PnL.tsx**

In `frontend/src/pages/PnL.tsx`, add the following new state variables (alongside existing `items`, `venues`, etc.):
```typescript
const [fund, setFund] = useState<FundBalance | null>(null)
const [newEntryDesc, setNewEntryDesc] = useState('')
const [newEntryAmount, setNewEntryAmount] = useState('')
const [addingEntry, setAddingEntry] = useState(false)
```

Update the import line to include the new types:
```typescript
import type { Session, PnLResult, Venue, FundBalance } from '../types'
```

In the `useEffect` `load()` function, add a parallel fund fetch:
```typescript
const [allSessions, venueList, fundBalance] = await Promise.all([
  api.get<Session[]>('/api/v1/sessions', signal),
  api.get<Venue[]>('/api/v1/venues', signal),
  api.get<FundBalance>('/api/v1/fund/balance', signal),
])
setFund(fundBalance)
```
(Replace the existing two-element `Promise.all` with this three-element version.)

Also ensure `setFundLoading(false)` is placed in the `finally` block alongside the existing `setLoading(false)`:
```typescript
    } finally {
      setLoading(false)
    }
```
(`fund` uses the shared `loading` state — no separate `fundLoading` needed.)

- [ ] **Step 3: Add handleAddFundEntry function**

Add this function inside the `PnL` component, before the `return`:
```typescript
async function handleAddFundEntry() {
  const amount = parseFloat(newEntryAmount)
  if (!newEntryDesc.trim() || isNaN(amount)) return
  setAddingEntry(true)
  try {
    await api.post('/api/v1/fund/entries', { description: newEntryDesc.trim(), amount })
    const updated = await api.get<FundBalance>('/api/v1/fund/balance')
    setFund(updated)
    setNewEntryDesc('')
    setNewEntryAmount('')
  } finally {
    setAddingEntry(false)
  }
}
```

- [ ] **Step 4: Add fund balance section to PnL.tsx JSX**

Add the fund balance section **before** the existing session list. Find the main `return (` in `PnL.tsx` and insert the following block at the top of the page content (after the back button / header):

```tsx
{/* Fund Balance Section */}
{loading ? (
  <div className="rounded-xl bg-gray-800 p-4 animate-pulse border border-gray-700 mb-6">
    <div className="h-4 w-40 bg-gray-700 rounded mb-2" />
    <div className="h-3 w-28 bg-gray-700 rounded" />
  </div>
) : fund ? (
  <div className="rounded-xl bg-gray-800 border border-gray-700 p-4 mb-6">
    <h2 className="font-semibold text-white mb-3">💰 Fund Balance</h2>
    <div className="space-y-1 mb-3">
      {fund.entries.map(entry => (
        <div key={entry.id} className="flex justify-between text-sm text-gray-300">
          <span>{entry.description}</span>
          <span className={entry.amount >= 0 ? 'text-green-400' : 'text-red-400'}>
            {entry.amount >= 0 ? '+' : ''}${entry.amount.toFixed(2)}
          </span>
        </div>
      ))}
    </div>
    <div className="flex justify-between font-semibold text-white border-t border-gray-600 pt-2 mb-3">
      <span>Manual Entries Total</span>
      <span className={fund.entries_total >= 0 ? 'text-green-400' : 'text-red-400'}>
        {fund.entries_total >= 0 ? '+' : ''}${fund.entries_total.toFixed(2)}
      </span>
    </div>
    {/* Add new entry form */}
    <div className="flex gap-2">
      <input
        className="flex-1 rounded bg-gray-700 border border-gray-600 px-2 py-1 text-sm text-white placeholder-gray-400"
        placeholder="Description (e.g. Opening balance)"
        value={newEntryDesc}
        onChange={e => setNewEntryDesc(e.target.value)}
      />
      <input
        className="w-24 rounded bg-gray-700 border border-gray-600 px-2 py-1 text-sm text-white placeholder-gray-400"
        placeholder="Amount"
        type="number"
        step="0.01"
        value={newEntryAmount}
        onChange={e => setNewEntryAmount(e.target.value)}
      />
      <button
        className="rounded bg-blue-600 px-3 py-1 text-sm text-white disabled:opacity-50"
        disabled={addingEntry || !newEntryDesc.trim() || !newEntryAmount}
        onClick={handleAddFundEntry}
      >
        Add
      </button>
    </div>
    <p className="text-xs text-gray-500 mt-1">Note: shuttle batch purchases are auto-recorded when added in Inventory. Use this form for opening balance (e.g. +$200) or manual adjustments (e.g. court deposit: −$80).</p>
  </div>
) : null}
```

- [ ] **Step 5: Build frontend to verify no TypeScript errors**

```bash
cd frontend && npm run build 2>&1 | tail -20
```
Expected: `✓ built in ...` with no TypeScript errors

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/pages/PnL.tsx
git commit -m "feat: add fund balance section to PnL page"
```

---

### Task 9: Frontend — Recruit Message Button & Modal in SessionDetail

**Files:**
- Modify: `frontend/src/pages/SessionDetail.tsx`

> **Note:** This task depends on Task 6 (POST `/api/v1/sessions/{id}/recruit` endpoint). Ensure Task 6 is deployed/running before manual testing.

- [ ] **Step 1: Add recruit state variables**

In `frontend/src/pages/SessionDetail.tsx`, add these new state variables alongside existing `showCancelModal`, `saving`, etc.:
```typescript
const [recruitMessage, setRecruitMessage] = useState<string | null>(null)
const [recruiting, setRecruiting] = useState(false)
const [recruitError, setRecruitError] = useState<string | null>(null)
const [copied, setCopied] = useState(false)
```

- [ ] **Step 2: Add handleGenerateRecruit function**

Add inside the component body before `return`:
```typescript
async function handleGenerateRecruit() {
  if (!session) return
  setRecruiting(true)
  setRecruitError(null)
  try {
    const res = await api.post<{ message: string }>(`/api/v1/sessions/${session.id}/recruit`, {})
    setRecruitMessage(res.message)
  } catch (err) {
    setRecruitError(err instanceof Error ? err.message : 'Failed to generate message')
  } finally {
    setRecruiting(false)
  }
}

async function handleCopyRecruit() {
  if (!recruitMessage) return
  await navigator.clipboard.writeText(recruitMessage)
  setCopied(true)
  setTimeout(() => setCopied(false), 2000)
}
```

- [ ] **Step 3: Add Recruit button in the action buttons area**

In the SessionDetail JSX, find the section that contains the "Publish", "Cancel", etc. action buttons and add the recruit button. It should only appear for `published` sessions:

```tsx
{session.status === 'published' && (
  <button
    onClick={handleGenerateRecruit}
    disabled={recruiting}
    className="rounded-lg bg-purple-700 px-4 py-2 text-sm text-white hover:bg-purple-600 disabled:opacity-50"
  >
    {recruiting ? 'Generating…' : '📣 Recruit Players'}
  </button>
)}
{recruitError && (
  <p className="text-sm text-red-400">{recruitError}</p>
)}
```

- [ ] **Step 4: Add recruit message modal**

Add the following modal at the bottom of the component (alongside the cancel modal):

```tsx
{/* Recruit Message Modal */}
{recruitMessage && (
  <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
    <div className="w-full max-w-lg rounded-xl bg-gray-800 border border-gray-600 p-5 shadow-xl">
      <h3 className="text-lg font-semibold text-white mb-3">📣 Recruit Message</h3>
      <p className="text-xs text-gray-400 mb-2">Sent to admin group. Copy and share as needed.</p>
      <pre className="rounded bg-gray-900 p-3 text-sm text-gray-200 whitespace-pre-wrap mb-4 border border-gray-700">
        {recruitMessage}
      </pre>
      <div className="flex gap-3">
        <button
          onClick={handleCopyRecruit}
          className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-500"
        >
          {copied ? '✅ Copied!' : '📋 Copy'}
        </button>
        <button
          onClick={() => { setRecruitMessage(null); setCopied(false) }}
          className="rounded bg-gray-700 px-4 py-2 text-sm text-gray-300 hover:bg-gray-600"
        >
          Close
        </button>
      </div>
    </div>
  </div>
)}
```

- [ ] **Step 5: Build frontend to verify no TypeScript errors**

```bash
cd frontend && npm run build 2>&1 | tail -20
```
Expected: `✓ built in ...` with no TypeScript errors

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/SessionDetail.tsx
git commit -m "feat: add Recruit Players button and copy modal to SessionDetail"
```

---

## Wave 4 — Integration Test (Task 10)

### Task 10: E2E Integration Test

**Files:**
- Create: `backend/tests/test_e2e_new_features.py`

- [ ] **Step 1: Write the E2E test**

The E2E test uses `TestClient` to exercise HTTP endpoints end-to-end. Formatter/service-level behavior is already covered by unit tests — this file focuses on cross-layer integration.

```python
# backend/tests/test_e2e_new_features.py
"""
E2E integration tests for the 5 new features.
Exercises HTTP endpoints via TestClient with mocked DB and bot.
Formatter/service-only behavior is tested in the unit test files.
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

_TS = "2026-01-01T10:00:00+00:00"
_SESSION_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
_VENUE_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
_ENTRY_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
_FUND_ID = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"

_SESSION_ROW = {
    "id": _SESSION_ID, "venue_id": _VENUE_ID,
    "date": "2026-05-31", "start_time": "20:00:00", "end_time": "22:00:00",
    "duration_hours": 2.0, "courts_booked": "Court 1 & 2", "num_courts": 2,
    "min_skill_level": "HB", "max_skill_level": "LI",
    "pub_fee": 12.0, "max_pax": 12, "status": "published",
    "telegram_message_id": 99999, "paynow_player_id": None, "created_at": _TS,
}
_VENUE_ROW = {
    "id": _VENUE_ID, "name": "Fengshan CC",
    "court_cost_per_hour": 15.0, "default_pub_fee": 12.0, "created_at": _TS,
}
_ROSTER_ROW = {
    "id": _ENTRY_ID, "session_id": _SESSION_ID,
    "player_id": None, "guest_name": "Alice", "player_type": "guest",
    "payment_status": "verified_paid", "is_waitlisted": False, "position": 1,
    "joined_at": _TS, "created_at": _TS,
}
_FUND_ENTRY_ROW = {
    "id": _FUND_ID, "description": "Opening balance", "amount": 200.0, "created_at": _TS,
}


def _make_client(db_responses: list) -> TestClient:
    """Build a TestClient with DB mocked to return sequential responses and auth bypassed."""
    from app.main import app
    from app.dependencies import require_admin

    call_count = [0]

    def mock_execute():
        m = MagicMock()
        idx = call_count[0]
        call_count[0] += 1
        if idx < len(db_responses):
            m.data = db_responses[idx]
        else:
            m.data = []
        return m

    mock_client = MagicMock()
    mock_client.table.return_value.select.return_value.eq.return_value.execute = mock_execute
    mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute = mock_execute
    mock_client.table.return_value.select.return_value.order.return_value.execute = mock_execute
    mock_client.table.return_value.select.return_value.execute = mock_execute
    mock_client.table.return_value.insert.return_value.execute = mock_execute

    app.dependency_overrides[require_admin] = lambda: "test-admin"

    with (
        patch("app.db.client._service_client", mock_client),
        patch("app.bot.runner.bot_runner.post_recruit_message", new=AsyncMock()),
        patch("app.bot.runner.bot_runner.delete_session_message", new=AsyncMock()),
    ):
        client = TestClient(app, raise_server_exceptions=True)
        yield client

    app.dependency_overrides.clear()


# ── Feature 4: POST /sessions/{id}/recruit ────────────────────────────────────

def test_recruit_endpoint_returns_formatted_message():
    """POST /recruit returns a message containing slots, venue, shuttle line."""
    import contextlib

    db_responses = [
        [_SESSION_ROW],     # session_service.get_by_id
        [_VENUE_ROW],       # venue_service.get_by_id
        [_ROSTER_ROW],      # roster_service.get_session_roster
    ]

    with contextlib.contextmanager(_make_client)(db_responses) as client:
        resp = client.post(f"/api/v1/sessions/{_SESSION_ID}/recruit")

    assert resp.status_code == 200
    body = resp.json()
    assert "message" in body
    msg = body["message"]
    assert "Fengshan CC" in msg
    assert "RSL Ultimate shuttles provided" in msg
    assert "[" in msg and "slot" in msg


# ── Feature 3: Fund entries endpoint ─────────────────────────────────────────

def test_fund_create_entry_endpoint():
    """POST /fund/entries creates an entry and returns it."""
    import contextlib

    db_responses = [[_FUND_ENTRY_ROW]]  # insert response

    with contextlib.contextmanager(_make_client)(db_responses) as client:
        resp = client.post("/api/v1/fund/entries", json={"description": "Opening balance", "amount": 200.0})

    assert resp.status_code == 201
    body = resp.json()
    assert body["description"] == "Opening balance"
    assert body["amount"] == pytest.approx(200.0)


def test_fund_balance_endpoint():
    """GET /fund/balance returns entries_total summing all entries."""
    import contextlib

    rows = [
        {"id": _FUND_ID, "description": "Opening", "amount": 200.0, "created_at": _TS},
        {"id": "ff" * 16, "description": "Shuttles", "amount": -40.0, "created_at": _TS},
    ]
    db_responses = [rows]  # get_entries → order query

    with contextlib.contextmanager(_make_client)(db_responses) as client:
        resp = client.get("/api/v1/fund/balance")

    assert resp.status_code == 200
    body = resp.json()
    assert body["entries_total"] == pytest.approx(160.0)


# ── Feature 5: delete_session_message on complete ────────────────────────────

@pytest.mark.asyncio
async def test_delete_session_message_calls_bot_delete():
    """BotRunner.delete_session_message calls bot.delete_message with the stored message_id."""
    from app.bot.runner import BotRunner
    from app.models.session import Session
    from datetime import date, time

    runner = BotRunner()
    runner._app = MagicMock()
    runner._app.bot.delete_message = AsyncMock()

    session = Session(
        id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        venue_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        date=date(2026, 5, 31), start_time=time(20, 0), end_time=time(22, 0),
        duration_hours=2.0, courts_booked="C1", num_courts=1,
        min_skill_level="HB", max_skill_level="LI",
        pub_fee=12.0, max_pax=12, status="completed",
        telegram_message_id=987654,
        created_at=datetime.now(timezone.utc),
    )
    await runner.delete_session_message(session)

    runner._app.bot.delete_message.assert_called_once()
    assert runner._app.bot.delete_message.call_args.kwargs["message_id"] == 987654


@pytest.mark.asyncio
async def test_delete_session_message_noop_if_no_telegram_id():
    from app.bot.runner import BotRunner
    from app.models.session import Session
    from datetime import date, time

    runner = BotRunner()
    runner._app = MagicMock()
    runner._app.bot.delete_message = AsyncMock()

    session = Session(
        id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        venue_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        date=date(2026, 5, 31), start_time=time(20, 0), end_time=time(22, 0),
        duration_hours=2.0, courts_booked="C1", num_courts=1,
        min_skill_level="HB", max_skill_level="LI",
        pub_fee=12.0, max_pax=12, status="completed",
        telegram_message_id=None,
        created_at=datetime.now(timezone.utc),
    )
    await runner.delete_session_message(session)

    runner._app.bot.delete_message.assert_not_called()


# ── Cross-service: shuttle auto-deducts fund ─────────────────────────────────

def test_shuttle_create_auto_deducts_fund_entry():
    """Creating a batch (remaining_count>0) inserts a negative fund entry for purchase cost."""
    import app.services.shuttle_service as shuttle_service
    from app.models.shuttle import ShuttleBatchCreate
    from unittest.mock import patch, MagicMock
    from datetime import datetime, timezone

    batch_row = {
        "id": "aabb" * 8, "batch_name": "RSL May", "brand": "RSL Ultimate",
        "owner_label": None, "cost_per_tube": 20.0, "shuttles_per_tube": 12,
        "cost_per_shuttle": 1.67, "remaining_count": 24, "is_active": True,
        "purchased_at": None, "created_at": datetime.now(timezone.utc).isoformat(),
    }
    client = MagicMock()
    client.table.return_value.insert.return_value.execute.return_value.data = [batch_row]

    with (
        patch("app.services.shuttle_service.get_service_client", return_value=client),
        patch("app.services.shuttle_service.fund_service.add_entry") as mock_add,
    ):
        shuttle_service.create(ShuttleBatchCreate(
            batch_name="RSL May", brand="RSL Ultimate",
            cost_per_tube=20.0, shuttles_per_tube=12, remaining_count=24,
        ))

    mock_add.assert_called_once()
    entry_arg = mock_add.call_args[0][0]
    assert entry_arg.amount == pytest.approx(-40.0)  # ceil(24/12) * $20 = $40
    assert "RSL May" in entry_arg.description


def test_shuttle_create_zero_count_does_not_deduct_fund():
    """Creating a batch with remaining_count=0 skips the fund deduction."""
    import app.services.shuttle_service as shuttle_service
    from app.models.shuttle import ShuttleBatchCreate
    from datetime import datetime, timezone

    batch_row = {
        "id": "aabb" * 8, "batch_name": "Empty", "brand": "Yonex",
        "owner_label": None, "cost_per_tube": 20.0, "shuttles_per_tube": 12,
        "cost_per_shuttle": 1.67, "remaining_count": 0, "is_active": True,
        "purchased_at": None, "created_at": datetime.now(timezone.utc).isoformat(),
    }
    client = MagicMock()
    client.table.return_value.insert.return_value.execute.return_value.data = [batch_row]

    with (
        patch("app.services.shuttle_service.get_service_client", return_value=client),
        patch("app.services.shuttle_service.fund_service.add_entry") as mock_add,
    ):
        shuttle_service.create(ShuttleBatchCreate(
            batch_name="Empty", brand="Yonex",
            cost_per_tube=20.0, shuttles_per_tube=12, remaining_count=0,
        ))

    mock_add.assert_not_called()
```

- [ ] **Step 2: Run all tests**

```bash
cd backend && python -m pytest tests/test_e2e_new_features.py -v
```
Expected: PASS (all tests)

- [ ] **Step 3: Run full test suite to check for regressions**

```bash
cd backend && python -m pytest tests/ -v 2>&1 | tail -30
```
Expected: All previously-passing tests still pass.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_e2e_new_features.py
git commit -m "test: add E2E integration tests for 5 new bot/fund features"
```

---

## Final: Build Verification

- [ ] **Verify backend starts cleanly**

```bash
cd backend && python -c "from app.main import app; print('Backend OK')"
```
Expected: `Backend OK`

- [ ] **Verify frontend builds without errors**

```bash
cd frontend && npm run build 2>&1 | tail -5
```
Expected: `✓ built in ...`

- [ ] **Run full backend test suite**

```bash
cd backend && python -m pytest tests/ -v 2>&1 | tail -30
```
Expected: All tests pass (count includes new tests from this feature set).

- [ ] **Final commit**

```bash
git add -A
git commit -m "feat: complete bot/fund feature set (withdraw, help, fund ledger, recruit, delete-on-complete)"
```
