# Scripts

## import_excel.py

Seeds the Supabase database with historical data from `Badminton.xlsx`.

### Prerequisites

```bash
pip install -r scripts/requirements.txt
```

### Usage

Set environment variables:

```bash
export SUPABASE_URL=https://your-project.supabase.co
export SUPABASE_SERVICE_ROLE_KEY=your-service-role-key

export SUPABASE_URL=https://bluorxnssewypmgnnwgs.supabase.co
export SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJsdW9yeG5zc2V3eXBtZ25ud2dzIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3OTY4NDg3MCwiZXhwIjoyMDk1MjYwODcwfQ.ODsccO9ocnpqkiz2of4Vyp8rH2MVwEuBKBhVvW2t_fk
```

Then run from the repo root:

```bash
python scripts/import_excel.py
```

### What gets imported

| Sheet | Table | Notes |
|---|---|---|
| `Court List` | `venues` | 9 venues with court cost and default pub fee |
| `Member List` | `players` | Internal members (`is_internal=True`); unique names extracted from attendance log |
| `Pub List-Selection` | `players` | Public players (`is_internal=False`); skill level and notes imported where available |
| `Shuttle Purchase` | `shuttle_batches` | One row per (shuttle type × owner); all marked `is_active=False` |

### What is NOT imported

- **Historical sessions** (`Profit & Loss` sheet) — the data is denormalised and
  tightly coupled to the Excel layout; importing it reliably is error-prone.
  Start fresh sessions from the web app instead.
- **Roster entries** — depend on historical sessions which are not imported.

### Re-running

The script is safe to re-run.  Existing rows are detected by name (players, venues)
or by `batch_name + owner_label` (shuttle batches) and silently skipped.
