# Supabase Migrations

SQL migration files for the Badminton Session Management App.

## Files

| File | Description |
|------|-------------|
| `migrations/001_schema.sql` | All 6 tables: `players`, `venues`, `shuttle_batches`, `sessions`, `roster_entries`, `shuttle_usage` |
| `migrations/002_rls.sql` | Row Level Security — authenticated users only |
| `migrations/003_seed.sql` | Seed data: venues from the Court List |

## Applying Migrations

### Option A — Supabase Dashboard (SQL Editor)

1. Open your project in [app.supabase.com](https://app.supabase.com)
2. Go to **SQL Editor**
3. Paste and run each file in order: `001_schema.sql` → `002_rls.sql` → `003_seed.sql`

### Option B — Supabase CLI

```bash
# Link to your project (one-time)
supabase link --project-ref <your-project-ref>

# Push all migrations
supabase db push
```

> **Note:** The CLI requires a `supabase/config.toml`. If you don't have one, use Option A or run `supabase init` first.

## Re-running / Idempotency

- `001_schema.sql` uses `CREATE TABLE IF NOT EXISTS` — safe to re-run.
- `002_rls.sql` uses `CREATE POLICY` — will error if policies already exist; drop them first if needed.
- `003_seed.sql` uses `INSERT ... ON CONFLICT DO NOTHING` — safe to re-run.
