# Session Improvements Design

> Spec for 9 improvements to session management, roster, Telegram bot, and P&L.

---

## Item 1: Empty roster on create
New sessions should start with an empty roster. Remove the auto-populate block that adds all internal players to `roster_entries` during `session_service.create()`.

## Item 2: Edit session inline
Admin can edit all session fields from the SessionDetail page. An "Edit" button reveals an inline form pre-populated with current values. On save, the frontend calls `PATCH /api/v1/sessions/{id}`. `SessionUpdate` model must include `venue_id: UUID | None` (currently missing).

## Item 3: Default skill levels HB / LI
`SessionCreate.min_skill_level` default changed from `"LI"` → `"HB"`. `SessionCreate.max_skill_level` default changed from `"MI"` → `"LI"`. Same defaults applied in `NewSession.tsx` form state.

## Item 4: Mark any player as paid
The "Verify ✓" button in the roster table currently only appears for `pending_verification` entries. Change it to appear for **all** entries not already `verified_paid` (including `unpaid`). No backend change needed.

## Item 5: Cancel session with reason
- New DB status: `cancelled` (terminal — cannot transition back).
- New endpoint: `POST /api/v1/sessions/{id}/cancel` with body `{ "reason": "..." }`.
- Service: validates session is `internal` or `published` (not `completed`/`cancelled`), updates status.
- Bot: posts cancellation message in Telegram group:
  ```
  ❌ Session Cancelled
  📅 [Date] [Time] · [Venue]
  Reason: [admin's message]
  Sorry for the inconvenience! 🙏
  ```
- Frontend: "Cancel Session" button opens a modal with a reason textarea. On confirm, calls cancel endpoint. Status badge added for `cancelled` (red).

## Item 6: Loading spinner fix
`SessionDetail.tsx`'s `useEffect` doesn't reset `loading` to `true` when navigating between sessions (same component instance, different `id`). Fix: add `setLoading(true); setSession(null); setError(null)` at the top of the effect (before the async function) so the skeleton always shows when fetching.

## Item 7: Court numbers in Telegram
`message_formatter.format_session_announcement` currently shows `🏟️ Courts: {session.courts_booked}`. Change to `🏟️ {session.courts_booked}` — drop the "Courts: " prefix. This shows the admin-entered label (e.g., "3 & 4") directly without redundancy.

## Item 8: Fix 422 on complete session
Two bugs in `SessionDetail.tsx handleComplete`:
1. `ShuttleModal` maps quantities to `{ batch_id, quantity }` — backend `ShuttleUsageCreate` expects `count_used`, not `quantity`.
2. `api.post(..., { shuttle_usages: usages })` wraps the list in an object — backend `Body(default=[])` expects a raw JSON array.
Fix: rename field to `count_used` and send the array directly.

## Item 9: Internal players auto-verified at $0
When an internal player (`player.is_internal = True`) joins via Telegram bot, `roster_service.add_player()` sets `payment_status = "verified_paid"` instead of `"unpaid"`. P&L already excludes internal players from `total_fees_collected` (pre-existing logic in `pnl_service.get_session_pnl()`).

---

## Database
One new migration `006_add_cancelled_status.sql`:
- Update `sessions.status` CHECK constraint to include `'cancelled'`
- Update `roster_entries.payment_status` CHECK to include `'pending_verification'` (existing constraint only has `unpaid`/`verified_paid` — inconsistent with Python model)

## Testing
- E2E test `test_session_improvements_e2e.py`: create session (verify empty roster) → add internal player via bot (verify auto-paid) → cancel session with reason (verify status + bot message format)
- Unit: `test_message_formatter.py` updated for courts label change and cancellation format
