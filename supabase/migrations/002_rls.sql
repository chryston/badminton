-- =============================================================
-- Migration 002: Row Level Security
-- All tables are accessible only to authenticated users.
-- All authenticated users are admins — no public sign-up.
-- =============================================================

-- ------------------------------------------------------------
-- players
-- ------------------------------------------------------------
ALTER TABLE players ENABLE ROW LEVEL SECURITY;

CREATE POLICY "authenticated_full_access" ON players
    FOR ALL TO authenticated
    USING (true)
    WITH CHECK (true);

-- ------------------------------------------------------------
-- venues
-- ------------------------------------------------------------
ALTER TABLE venues ENABLE ROW LEVEL SECURITY;

CREATE POLICY "authenticated_full_access" ON venues
    FOR ALL TO authenticated
    USING (true)
    WITH CHECK (true);

-- ------------------------------------------------------------
-- shuttle_batches
-- ------------------------------------------------------------
ALTER TABLE shuttle_batches ENABLE ROW LEVEL SECURITY;

CREATE POLICY "authenticated_full_access" ON shuttle_batches
    FOR ALL TO authenticated
    USING (true)
    WITH CHECK (true);

-- ------------------------------------------------------------
-- sessions
-- ------------------------------------------------------------
ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "authenticated_full_access" ON sessions
    FOR ALL TO authenticated
    USING (true)
    WITH CHECK (true);

-- ------------------------------------------------------------
-- roster_entries
-- ------------------------------------------------------------
ALTER TABLE roster_entries ENABLE ROW LEVEL SECURITY;

CREATE POLICY "authenticated_full_access" ON roster_entries
    FOR ALL TO authenticated
    USING (true)
    WITH CHECK (true);

-- ------------------------------------------------------------
-- shuttle_usage
-- ------------------------------------------------------------
ALTER TABLE shuttle_usage ENABLE ROW LEVEL SECURITY;

CREATE POLICY "authenticated_full_access" ON shuttle_usage
    FOR ALL TO authenticated
    USING (true)
    WITH CHECK (true);
