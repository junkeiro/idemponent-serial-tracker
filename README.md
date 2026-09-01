# Idempotent Serial Tracker

Python + React tracker for pharmaceutical serialized-unit lifecycle events that
arrive out of order, duplicated, replayed, and with partial attributes.

## Database

SQLite. It is in-process, requires no Docker, and is sufficient for the exercise.
A single `events` table stores the raw event stream; all derived state is
recomputed from that table so the system is trivially order-independent.

## Run, seed, and test

Assumes Python 3.11+ and the repo root as working directory.

1. Install dependencies and start the server (two shell commands, the second
   stays running):

   ```bash
   python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
   .venv/bin/uvicorn app:app --host 127.0.0.1 --port 8000
   ```

2. Load demo data (one command, run from another terminal while the server is up):

   ```bash
   .venv/bin/python seed.py
   ```

3. Run tests (one command):

   ```bash
   .venv/bin/pytest
   ```

   The `test_app.py ........ [ 44%]` / `test_tracker.py .......... [100%]`
   lines are the **overall test-run progress** (8 of 18 tests and 10 of 18
   tests), not per-file code coverage.

The detail view is served at `http://127.0.0.1:8000/`. API endpoints are `POST
/events` and `GET /serials/{serial_id}`.

---

## Coverage (optional)

To see actual code coverage of `tracker.py` and `app.py`:

```bash
DATABASE_URL=:memory: .venv/bin/pytest --cov=tracker --cov=app
```

This reports 100% line coverage for both files.

## Acceptance criteria → tests

| AC | Test file | Test name(s) |
|----|-----------|--------------|
| AC1 idempotency | `test_tracker.py` | `test_idempotency_duplicate_event_id` |
| AC1 idempotency | `test_app.py` | `test_post_duplicate_event` |
| AC2 order independence | `test_tracker.py` | `test_order_independence`, `test_section_six_in_any_arrival_order` |
| AC2 order independence | `test_app.py` | `test_section_six_in_any_arrival_order` |
| AC3 no regress | `test_tracker.py` | `test_no_regress_late_received_does_not_overwrite` |
| AC4 invalid transition rejected | `test_tracker.py` | `test_invalid_transition_after_decommissioned` |
| AC4 invalid transition rejected | `test_app.py` | `test_invalid_transition_after_decommissioned` |
| AC5 §6 worked example | `test_tracker.py` | `test_section_six_worked_example` |
| AC5 §6 worked example | `test_app.py` | `test_section_six_in_any_arrival_order` |
| AC6 frontend milestone/rejected view | manual / `frontend/index.html` | open `http://127.0.0.1:8000/` after `seed.py` |
| AC7 run/seed/test commands | this README | verified by running the listed commands |
| AC8 scale/index answer | this README | "Scale question" section |

## Coverage

Run tests with coverage:

```bash
DATABASE_URL=:memory: .venv/bin/pytest --cov=tracker --cov=app --cov-report=term-missing --cov-report=html
```

The terminal output shows per-file percentages and missing lines. An HTML
report is generated in `htmlcov/index.html` — open it in a browser to see the
full annotated coverage view.

Current coverage: **100%** of `tracker.py` and `app.py`.

## How R1–R5 are enforced

All five rules collapse into one invariant: **the stored document for a serial
is a pure function of the deduplicated set of events, not of arrival order or
count.**

- **R1 Idempotency:** `events.event_id` is the primary key. `INSERT OR IGNORE`
  detects duplicates at the storage layer before any state is derived.
- **R2 Order independence:** `derive_serial_state()` sorts all events by
  `(event_time, event_id)` and walks the chain. The same set always produces the
  same document, no matter the insertion order.
- **R3 No regress / no overwrite:** `attrs` is built by iterating the sorted
  accepted events and assigning `attrs[key] = value` for each key present. A
  later accepted event overwrites an earlier value; an older event never
  removes a key that a newer event already set.
- **R4 Invalid transitions recorded:** during the chain walk, any event whose
  state is not a valid transition from the previous accepted state is placed in
  `rejected_events` with a reason. `Decommissioned` has no outgoing transitions,
  so nothing further is accepted.
- **R5 Concurrency:** a single `threading.Lock` serializes all writes. Two
  concurrent `POST /events` calls for the same serial are processed one at a
  time, so no read-modify-write cycle is lost. (Per-serial locks would be the
  production refinement; a global lock is the 60-minute choice.)

## Scale question: hundreds of millions of rows

Users need to filter by `lot`, `purchase order`, and `current_state`, paginated.

### Indexes

The raw `events` table is the wrong place to search at this scale. I would
maintain a materialized `serial_state` projection with the following schema:

```sql
CREATE TABLE serial_state (
    serial_id TEXT PRIMARY KEY,
    current_state TEXT NOT NULL,
    lot TEXT,
    po TEXT,
    -- other frequently searched attributes as generated columns or extracted fields
    last_event_time TEXT NOT NULL
);

CREATE INDEX idx_serial_state_lot ON serial_state(lot);
CREATE INDEX idx_serial_state_po ON serial_state(po);
CREATE INDEX idx_serial_state_state ON serial_state(current_state);
CREATE INDEX idx_serial_state_lot_po ON serial_state(lot, po);
CREATE INDEX idx_serial_state_lot_po_state ON serial_state(lot, po, current_state);
```

`lot` and `po` are extracted from the merged `attrs` during the state derivation
and stored as first-class columns because JSON value lookups (`json_extract` or
equivalent) cannot use a B-tree index efficiently at this volume.

### Queries

- By `lot` and `po`:
  ```sql
  SELECT serial_id, current_state, lot, po
  FROM serial_state
  WHERE lot = ? AND po = ?
  ORDER BY last_event_time, serial_id
  LIMIT ?;
  ```

- By `current_state`:
  ```sql
  SELECT serial_id, current_state, lot, po
  FROM serial_state
  WHERE current_state = ?
  ORDER BY last_event_time, serial_id
  LIMIT ?;
  ```

- Combined:
  ```sql
  SELECT serial_id, current_state, lot, po
  FROM serial_state
  WHERE lot = ? AND po = ? AND current_state = ?
  ORDER BY last_event_time, serial_id
  LIMIT ?;
  ```

### Pagination

Use **cursor (keyset) pagination**, not `OFFSET`. After the first page, the next
request includes the `(last_event_time, serial_id)` of the last row, and the
query adds `WHERE (last_event_time, serial_id) > (?, ?)`. `OFFSET` at hundreds of
millions of rows is an O(n) full scan and must be refused.

### What I would refuse to do at this size

- **Search inside JSON `attrs` without precomputed columns/indexes.** e.g.
  `WHERE json_extract(attrs, '$.lot') = ?` on `events` will full-scan and is not
  viable.
- **`SELECT DISTINCT serial_id` or `OFFSET` pagination** on the event stream.
- **Ad-hoc filters on arbitrary attr keys** unless the keys are promoted to
  indexed columns and the workload justifies it.
- **Run the derivation (`derive_serial_state`) at query time** for search
  results; the materialized `serial_state` table must be kept up to date on
  every write.

## What was not built

- Real concurrency stress test (R5 global lock was used; per-serial locks and a
  load test are post-timebox).
- Docker / docker compose.
- Real paginated search endpoint; only the design is in this README.
- CI pipeline.
