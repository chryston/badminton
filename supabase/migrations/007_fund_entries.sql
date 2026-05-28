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
