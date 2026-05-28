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
