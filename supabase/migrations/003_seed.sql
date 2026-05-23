-- =============================================================
-- Migration 003: Seed Data
-- Idempotent — safe to run multiple times.
-- Source: Excel Court List (Sheet 10) + historical session data.
-- =============================================================

-- ------------------------------------------------------------
-- venues
-- ------------------------------------------------------------
INSERT INTO venues (name, court_cost_per_hour, default_pub_fee) VALUES
    ('Cereza',            27.25, 16),
    ('Expo Weekday',      26.00, 16),
    ('Siglap CC',         18.00, 14),
    ('Changi Simei CC',    6.00, 12),
    ('Fengshan CC',        8.00, 12),
    ('Kaki Bukit CC',      6.00, 12)
ON CONFLICT (name) DO NOTHING;
