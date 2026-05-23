-- =============================================================
-- Migration 001: Schema
-- Creates all 6 tables for the Badminton Session Management App
-- =============================================================

-- ------------------------------------------------------------
-- players
-- Represents every player (internal members and external guests).
-- Only admins have auth_user_id; telegram_id set when joining via bot.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS players (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    auth_user_id    uuid        REFERENCES auth.users(id) ON DELETE SET NULL,
    telegram_id     bigint      UNIQUE,
    name            text        NOT NULL,
    phone           text,
    skill_level     text        CHECK (skill_level IN ('HB', 'LI', 'MB')),
    is_internal     boolean     NOT NULL DEFAULT false,
    is_admin        boolean     NOT NULL DEFAULT false,
    notes           text,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_players_telegram_id ON players (telegram_id);

-- ------------------------------------------------------------
-- venues
-- Badminton halls with their pricing defaults.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS venues (
    id                    uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    name                  text        NOT NULL UNIQUE,
    court_cost_per_hour   numeric     NOT NULL,
    default_pub_fee       numeric     NOT NULL,
    created_at            timestamptz NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------
-- shuttle_batches
-- Tracks batches of shuttlecocks purchased, with cost breakdown.
-- cost_per_shuttle is stored as cost_per_tube / shuttles_per_tube.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS shuttle_batches (
    id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_name          text        NOT NULL,
    brand               text        NOT NULL,
    owner_label         text,
    cost_per_tube       numeric     NOT NULL,
    shuttles_per_tube   int         NOT NULL,
    cost_per_shuttle    numeric     NOT NULL,
    remaining_count     int         NOT NULL DEFAULT 0,
    is_active           boolean     NOT NULL DEFAULT true,
    purchased_at        date,
    created_at          timestamptz NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------
-- sessions
-- A single badminton session at a venue.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sessions (
    id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    venue_id            uuid        NOT NULL REFERENCES venues(id),
    date                date        NOT NULL,
    start_time          time        NOT NULL,
    end_time            time        NOT NULL,
    courts_booked       text        NOT NULL,
    num_courts          int         NOT NULL DEFAULT 1,
    skill_level         text        NOT NULL DEFAULT 'HB - LI',
    pub_fee             numeric     NOT NULL,
    max_pax             int         NOT NULL,
    status              text        NOT NULL DEFAULT 'internal'
                            CHECK (status IN ('internal', 'published', 'completed')),
    telegram_message_id bigint,
    paynow_player_id    uuid        REFERENCES players(id),
    created_at          timestamptz NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------
-- roster_entries
-- Tracks who is in a session, their payment status and position.
-- Either player_id or guest_name must be set (enforced by constraint).
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS roster_entries (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      uuid        NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    player_id       uuid        REFERENCES players(id) ON DELETE SET NULL,
    guest_name      text,
    player_type     text        NOT NULL CHECK (player_type IN ('registered', 'guest')),
    payment_status  text        NOT NULL DEFAULT 'unpaid'
                        CHECK (payment_status IN ('unpaid', 'verified_paid')),
    is_waitlisted   boolean     NOT NULL DEFAULT false,
    position        int         NOT NULL,
    joined_at       timestamptz NOT NULL DEFAULT now(),
    created_at      timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT player_or_guest         CHECK (player_id IS NOT NULL OR guest_name IS NOT NULL),
    CONSTRAINT unique_player_per_session UNIQUE (session_id, player_id)
);

CREATE INDEX IF NOT EXISTS idx_roster_entries_session_id ON roster_entries (session_id);

-- ------------------------------------------------------------
-- shuttle_usage
-- Records how many shuttles from a batch were used in a session.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS shuttle_usage (
    id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id  uuid        NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    batch_id    uuid        NOT NULL REFERENCES shuttle_batches(id),
    count_used  int         NOT NULL CHECK (count_used > 0),
    created_at  timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT unique_batch_per_session UNIQUE (session_id, batch_id)
);
