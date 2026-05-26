-- Migration: Session Schema V2
-- Adds: min/max skill levels, duration_hours, GENERATED end_time, court_slots table, RPC
-- All changes are idempotent (safe to re-run)

-- ── Step 1: Add min_skill_level and max_skill_level columns ──────────────────
ALTER TABLE sessions
    ADD COLUMN IF NOT EXISTS min_skill_level text NOT NULL DEFAULT 'LI',
    ADD COLUMN IF NOT EXISTS max_skill_level text NOT NULL DEFAULT 'MI';

-- ── Step 2: Add duration_hours column ─────────────────────────────────────────
ALTER TABLE sessions
    ADD COLUMN IF NOT EXISTS duration_hours numeric(4,2) NOT NULL DEFAULT 2.0;

-- ── Step 3: Data migration — skill_level → min/max ────────────────────────────
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'sessions' AND column_name = 'skill_level'
    ) THEN
        UPDATE sessions
        SET
            min_skill_level = CASE
                WHEN skill_level ILIKE '%HB%' THEN 'HB'
                WHEN skill_level ILIKE '%MB%' THEN 'MB'
                WHEN skill_level ILIKE '%LB%' THEN 'LB'
                WHEN skill_level ILIKE '%LI%' THEN 'LI'
                WHEN skill_level ILIKE '%MI%' THEN 'MI'
                WHEN skill_level ILIKE '%HI%' THEN 'HI'
                ELSE 'LI'
            END,
            max_skill_level = CASE
                WHEN skill_level ILIKE '%LI%' THEN 'LI'
                WHEN skill_level ILIKE '%MI%' THEN 'MI'
                WHEN skill_level ILIKE '%HI%' THEN 'HI'
                WHEN skill_level ILIKE '%HB%' THEN 'HB'
                WHEN skill_level ILIKE '%MB%' THEN 'MB'
                WHEN skill_level ILIKE '%LB%' THEN 'LB'
                ELSE 'MI'
            END;
    END IF;
END $$;

-- ── Step 4: Add CHECK constraints on skill levels ────────────────────────────
ALTER TABLE sessions
    DROP CONSTRAINT IF EXISTS sessions_min_skill_level_check,
    ADD  CONSTRAINT sessions_min_skill_level_check
        CHECK (min_skill_level IN ('LB','MB','HB','LI','MI','HI','A'));

ALTER TABLE sessions
    DROP CONSTRAINT IF EXISTS sessions_max_skill_level_check,
    ADD  CONSTRAINT sessions_max_skill_level_check
        CHECK (max_skill_level IN ('LB','MB','HB','LI','MI','HI','A'));

-- ── Step 5: Backfill duration_hours for existing rows ────────────────────────
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'sessions' AND column_name = 'start_time'
    ) AND EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'sessions' AND column_name = 'end_time'
          AND is_generated = 'NEVER'
    ) THEN
        UPDATE sessions
        SET duration_hours = EXTRACT(EPOCH FROM (end_time - start_time)) / 3600
        WHERE duration_hours = 2.0
          AND start_time IS NOT NULL
          AND end_time IS NOT NULL;
    END IF;
END $$;

-- ── Step 6: Drop old skill_level column ──────────────────────────────────────
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
