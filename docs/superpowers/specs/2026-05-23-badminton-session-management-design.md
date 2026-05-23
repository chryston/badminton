# Badminton Session Management App — Design Spec

**Date:** 2026-05-23  
**Status:** Approved  
**Scope:** Full-stack web app + Telegram bot to replace Google Sheets + manual Telegram workflows

---

## 1. Problem Statement

Weekly badminton sessions are currently managed via:
- Google Sheets for player tracking, P&L, shuttle inventory
- Manual copy-pasting of formatted Telegram messages into a private group ("LOWKEY")
- Manual payment verification and roster list updates

This creates toil, errors, and context-switching. The app automates the full lifecycle: session creation → bot announcement → player sign-ups → payment verification → post-game P&L.

---

## 2. Architecture

### Deployment (Option A — All-in-One on Render)

```
Browser/Mobile  →  HTTPS  →  Render: FastAPI + Bot (single service)
                                  ↕
                             Supabase (PostgreSQL + Auth)
                                  ↕
Render: Bot (long polling)  ↔  Telegram API
```

- **Frontend:** React + Vite + Tailwind CSS, statically exported SPA hosted on **GitHub Pages**
- **Backend:** Python FastAPI on **Render free tier** (persistent service, not serverless)
- **Bot:** `python-telegram-bot` running in **long-polling mode** in the same Render process — keeps the service warm 24/7
- **Database:** Supabase (PostgreSQL) free tier
- **Auth:** Supabase Auth (email+password) — only admins have auth accounts

### Environments

| Variable | Dev/Staging | Production |
|---|---|---|
| `TELEGRAM_ADMIN_CHAT_ID` | dummy_admin group ID | real admin group ID |
| `TELEGRAM_LOWKEY_CHAT_ID` | dummy_lowkey group ID | real LOWKEY group ID |
| `SUPABASE_URL` | dev project | prod project |

Dev uses real bot token but points at dummy test groups. Swap two env vars to go live.

---

## 3. Database Schema

### `players`
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| auth_user_id | uuid nullable | Links to `auth.users` — set only for admins |
| telegram_id | bigint unique nullable | Set when player first joins via bot |
| name | text | |
| phone | text nullable | For PayNow reference |
| skill_level | enum(HB, LI, MB) | |
| is_internal | boolean default false | Internal members: auto-added to all sessions as verified_paid, not charged |
| is_admin | boolean default false | Can log in to dashboard |
| notes | text nullable | Toxicity level, general notes |
| created_at | timestamptz |

### `venues`
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| name | text | e.g. "Fengshan CC" |
| court_cost_per_hour | numeric | |
| default_pub_fee | numeric | Auto-populated when creating a session |
| created_at | timestamptz |

Pre-seeded from Excel Sheet 10: Cereza ($27.25/$16), Expo Weekday ($26/$16), Siglap CC ($18/$14), Changi Simei CC ($6/$12), Fengshan CC ($8/$12). Kaki Bukit CC to be confirmed.

### `shuttle_batches`
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| batch_name | text | e.g. "Ultimate (Nov 2025)" |
| brand | text | e.g. "RSL Ultimate" |
| owner_label | text nullable | e.g. "Belle & Boo" — preserves existing ownership tracking |
| cost_per_tube | numeric | |
| shuttles_per_tube | int | |
| cost_per_shuttle | numeric | Stored (cost_per_tube / shuttles_per_tube), editable for corrections |
| remaining_count | int | |
| is_active | boolean default true | Active = available for use in sessions |
| purchased_at | date nullable | |
| created_at | timestamptz |

Multiple batches can be active simultaneously (different owners, different price points).

### `sessions`
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| venue_id | uuid FK → venues | |
| date | date | |
| start_time | time | |
| end_time | time | |
| courts_booked | text | e.g. "1 & 2" (display string) |
| num_courts | int | For cost calculation |
| skill_level | text | e.g. "HB - LI" |
| pub_fee | numeric | Auto-filled from venue default, editable |
| max_pax | int | |
| status | enum(internal, published, completed) | |
| telegram_message_id | bigint nullable | Stored after bot posts; used for edits |
| paynow_player_id | uuid FK → players | Who receives PayNow for this session |
| created_at | timestamptz |

### `roster_entries`
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| session_id | uuid FK → sessions | |
| player_id | uuid FK → players nullable | Null for guest entries |
| guest_name | text nullable | For manually-added external players with no player record |
| player_type | enum(registered, guest) | |
| payment_status | enum(unpaid, verified_paid) | No "pending" state — admin-only verification |
| is_waitlisted | boolean default false | |
| position | int | Order in the public list (1-based, waitlist continues above max_pax) |
| joined_at | timestamptz | |
| created_at | timestamptz |

### `shuttle_usage`
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| session_id | uuid FK → sessions | |
| batch_id | uuid FK → shuttle_batches | |
| count_used | int | |
| created_at | timestamptz |

One session can have multiple shuttle_usage rows (when multiple active batches are used).

### RLS Policies

All tables are locked down to authenticated admins only:

```sql
-- Applied to all tables
CREATE POLICY "Admins only" ON <table>
  FOR ALL TO authenticated
  USING (true)  -- all authenticated users are admins (no public access)
  WITH CHECK (true);

-- Block all anonymous access
ALTER TABLE <table> ENABLE ROW LEVEL SECURITY;
```

The Telegram bot uses the **Supabase service role key** (bypasses RLS) via the FastAPI backend. The service role key is never exposed to the frontend.

---

## 4. API Endpoints (FastAPI)

All routes require `Authorization: Bearer <supabase_jwt>` except the bot webhook (uses internal token).

### Sessions
| Method | Path | Description |
|---|---|---|
| GET | `/sessions` | List sessions (with roster counts) |
| POST | `/sessions` | Create session (auto-adds internal members to roster) |
| GET | `/sessions/{id}` | Session detail + full roster |
| PATCH | `/sessions/{id}` | Update session (status, fields) |
| POST | `/sessions/{id}/publish` | Set status=published, trigger bot post |
| POST | `/sessions/{id}/complete` | Set status=completed, record shuttle usage, calculate P&L |

### Roster
| Method | Path | Description |
|---|---|---|
| POST | `/sessions/{id}/roster` | Manually add guest player |
| DELETE | `/sessions/{id}/roster/{entry_id}` | Remove player (admin), trigger waitlist promotion |
| POST | `/sessions/{id}/roster/{entry_id}/verify-payment` | Verify payment, trigger bot edit |

### Players
| Method | Path | Description |
|---|---|---|
| GET | `/players` | List all players |
| POST | `/players` | Create player |
| PATCH | `/players/{id}` | Update player |

### Inventory
| Method | Path | Description |
|---|---|---|
| GET | `/shuttle-batches` | List all batches |
| POST | `/shuttle-batches` | Create new batch |
| PATCH | `/shuttle-batches/{id}` | Update batch (adjust count, toggle active) |

### P&L
| Method | Path | Description |
|---|---|---|
| GET | `/pnl` | Summary across all completed sessions |
| GET | `/pnl/{session_id}` | P&L breakdown for one session |

> **Note:** The bot runs in the same process as FastAPI and calls `SessionService` / `RosterService` functions directly — no internal HTTP endpoints needed for bot↔backend communication.

---

## 5. Telegram Bot Design

### Bot runs in the same FastAPI process using long polling

```python
# main.py — starts both together
async def main():
    await asyncio.gather(
        start_fastapi(),
        start_telegram_bot_polling(),
    )
```

### Conversation State (in-memory)

The bot tracks pending name-collection conversations:
```python
pending_name_requests: dict[int, PendingJoin] = {}
# telegram_user_id → {session_id, chat_id, timestamp}
```

State is in-memory (fine for single-process Render deployment). Entries expire after 10 minutes.

### Message Formats

**LOWKEY group announcement (posted on Publish):**
```
📅 Date: 29 May 2026, Fri
🕐 Time: 7:30 pm – 9:30 pm
📍 Venue: Fengshan CC
🏸 Court No.: 1 & 2
⚡ Level: HB – LI
💸 Please transfer $12 per pax to Belle (+65 8339 6501)

1. Belle (member)
2. Boo (member)
3.
4.
...
12.

[Join ✋]
```

**LOWKEY group message (edited after each roster change):**
- `(paid)` appended when payment verified
- `(waitlist)` shown below numbered list
- Join button removed once max_pax reached and replaced with "Full 🔒"

**Admin group post (posted on Publish):**
```
📌 Posted to LOWKEY
29 May · Fengshan CC · Courts 1&2 · $12/pax · 7:30–9:30pm
```

### Bot Flows

**Join flow:**
1. Player taps [Join ✋] → bot receives callback
2. Check `players.telegram_id` — known? Skip to step 5
3. Bot DMs: "Hi! What's your name for the session on 29 May? 😊"
4. Player replies → bot creates/updates player record with `telegram_id`
5. Check session capacity → add to roster (or waitlist)
6. Bot answers callback: "You're in! 🎉" or "Added to waitlist 👍"
7. Bot edits LOWKEY message with updated roster

**Internal member auto-add:** When a session is created, all `is_internal=true` players are added as `verified_paid`. Admins can remove any internal member from a specific session if they're not playing (e.g. sick) — this does not affect their status in other sessions.

**Duplicate join:** Bot responds "You're already on the list! 😄" — idempotent.

**DM disabled:** Bot catches error, answers callback: "Please allow DMs from bots first, then try again."

---

## 6. Supabase Auth Flow (Static SPA on GitHub Pages)

```
1. Admin opens GitHub Pages URL
2. React app calls supabase.auth.signInWithPassword()
3. Supabase returns JWT
4. React stores JWT in memory (not localStorage — security)
5. All FastAPI calls: Authorization: Bearer <jwt>
6. FastAPI verifies JWT with Supabase public key
7. On refresh: supabase.auth.getSession() restores session from cookie
```

Admin accounts are created manually by seeding Supabase Auth (no public sign-up).

---

## 7. Shuttle Inventory & Correction Workflow

- **Auto-deduct:** When a session is completed, admin enters `count_used` per batch → system decrements `remaining_count`
- **Manual override:** Admin can directly edit `remaining_count` on any batch (audit trail: Supabase logs)
- **Correction flow:** If wrong data was entered, admin edits the batch `remaining_count` and optionally the `shuttle_usage` row for that session — no SQL required (Supabase Table Editor)
- **New batch:** Admin taps "+ New Batch", fills in name/brand/owner/cost/tubes/count, saves

---

## 8. Data Import (One-Time Migration)

A Python script `scripts/import_excel.py` will:
1. Read `Badminton.xlsx`
2. Seed `venues` from Sheet 10 (Court List)
3. Seed `players` from Sheet 9 (Pub List-Selection) as `is_internal=false`
4. Seed internal `players` from unique names in Sheet 4 (Member List) as `is_internal=true`
5. Seed `shuttle_batches` from Sheet 5 (Shuttle Purchase) with `owner_label`
6. Seed historical `sessions` + `roster_entries` + `shuttle_usage` from Sheets 2, 3, 4, 6–8

Script is idempotent (upsert by name/date). Targets the **dev Supabase project** first.

---

## 9. Error Handling

| Scenario | Handling |
|---|---|
| Player has DMs disabled | Bot catches `Forbidden` error on DM send, answers callback: "Enable DMs first" |
| Session full when joining | Player added to waitlist, bot notifies: "Session full — you're #1 on the waitlist" |
| Duplicate join | Idempotent check on `(session_id, telegram_id)`, bot responds "Already registered" |
| Telegram message edit fails (deleted) | Log error, set `telegram_message_id = NULL` on session, continue |
| Supabase unavailable | FastAPI returns 503, frontend shows error toast; bot retries once after 2s |
| JWT expired | Supabase client auto-refreshes; if refresh fails, redirect to login |
| Render cold start (never cold — long polling) | N/A — bot polling keeps process alive |

---

## 10. Testing Strategy

**Philosophy:** Test behavior not implementation. Use real classes. Fail fast. At least one E2E test per major flow.

### E2E Integration Tests (pytest + httpx + test Supabase project)

**Test 1 — Full session lifecycle:**
```
create session → publish → assert bot posts to dummy_lowkey
→ simulate player join callback → assert roster entry created
→ admin verify payment → assert bot edits message with "(paid)"
→ complete session with shuttle_usage → assert P&L calculated correctly
→ assert shuttle remaining_count decremented
```

**Test 2 — Waitlist promotion:**
```
create session (max_pax=1) with 1 internal member
→ pub player joins → assert waitlisted
→ admin removes internal member → assert pub player promoted to roster
→ assert bot sends DM notification to promoted player
→ assert LOWKEY message updated
```

**Test 3 — Known vs unknown player join:**
```
simulate join from unknown telegram_id → assert DM sent asking for name
→ simulate name reply → assert player created → assert roster entry created
simulate second join from same telegram_id (different session)
→ assert DM NOT sent (skips to direct join)
```

### Unit Tests

- P&L calculation function (pure function, no DB)
- Telegram message formatting (roster → message string)
- Fee auto-calculation from venue

---

## 11. Staging → Production Rollout

1. Deploy with `TELEGRAM_ADMIN_CHAT_ID` and `TELEGRAM_LOWKEY_CHAT_ID` pointing to dummy test groups
2. Run full E2E test suite against dummy groups
3. Import Excel data to dev Supabase, validate all historical data looks correct
4. Admin team reviews dashboard with real historical data
5. When satisfied: update 2 env vars to real group IDs → redeploy → done

---

## 12. Project Structure

```
badminton/
├── frontend/                    # React + Vite + Tailwind
│   ├── src/
│   │   ├── pages/               # Sessions, Players, Inventory, PnL
│   │   ├── components/          # RosterCard, SessionCard, PaymentButton
│   │   ├── hooks/               # useSession, useRoster, useAuth
│   │   └── lib/                 # supabase client, api client
│   └── vite.config.ts
├── backend/                     # FastAPI + python-telegram-bot
│   ├── app/
│   │   ├── main.py              # Starts FastAPI + bot polling together
│   │   ├── routers/             # sessions, players, inventory, pnl, bot
│   │   ├── models/              # Pydantic schemas
│   │   ├── services/            # SessionService, BotService, PnLService
│   │   └── db/                  # Supabase client, query helpers
│   ├── tests/                   # pytest E2E + unit tests
│   └── requirements.txt
├── scripts/
│   └── import_excel.py          # One-time data migration
├── supabase/
│   └── migrations/              # SQL schema + RLS policies
└── docs/
    └── superpowers/specs/
        └── 2026-05-23-badminton-session-management-design.md
```

---

## 13. Key Decisions Log

| Decision | Choice | Reason |
|---|---|---|
| Deployment | All-in-one Render | Bot long-polling requires persistent process; keeps service warm |
| Bot mode | Long polling | Avoids need for public webhook URL in dev; simpler setup |
| Payment claiming | Admin-only | No bot involvement reduces complexity; matches current workflow |
| Member auto-add | On session creation | Internal members always play; saves manual steps |
| Conversation state | In-memory dict | Single process, expires after 10min; no DB overhead for transient state |
| Shuttle ownership | `owner_label` field | Preserves existing accounting without complex ownership model |
| Auth storage | Memory + Supabase cookie | Avoids XSS risk of localStorage for JWT |
| Data import | Python script (idempotent) | One-time migration with safety to re-run |
