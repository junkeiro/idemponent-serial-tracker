# PLAN.md — Idempotent Serial Tracker

## 1. Problem, in my own words

Serial lifecycle events arrive over a queue with no ordering, dedup, or
completeness guarantees. The system must compute one deterministic, replay-safe
"current state" document per serial from the **full set** of events it has ever
received, regardless of arrival order or duplication. Two write paths
(`POST /events`) and one read path (`GET /serials/{id}`) must all agree on the
same derivation defined in §5.0 of the brief: dedupe by `event_id`, sort by
`(event_time, event_id)`, walk the chain applying transition validation, merge
`attrs` with latest-wins/never-delete semantics.

## 2. Invariant to protect, and where it is enforced

The invariant is **"derived state is a pure function of the deduplicated event
set, not of arrival order or count."** (R1+R2 combined; R3/R4 are corollaries of
correctly implementing the §5.0 chain walk.)

This is enforced in **exactly one place**: a single `derive_serial_state(events)`
function that takes the raw stored events for a serial and returns
`{current_state, attrs, history, missing_milestones, rejected_events}`. Both the
write path (to compute the per-event outcome) and the read path (`GET`) call
this same function — never two implementations of the chain walk.

Concurrency (R5) is enforced at the storage boundary: writes for a given
`serial_id` happen inside a transaction that serializes on that serial (e.g. a
`SELECT ... FOR UPDATE`-style row lock, or SQLite's transaction serialization),
so two concurrent POSTs for the same serial cannot interleave a read-modify-write.

## 3. Data model

**Stored (source of truth):** raw events only, one row per `event_id`:

```
events(event_id PK, serial_id, state, event_time, seq, attrs JSON, received_at)
```

- `event_id` has a uniqueness constraint — this alone gives idempotency at the
  storage layer (R1): a duplicate insert is detected before any derivation runs.
- Nothing else is stored per serial as separate mutable columns. No
  "current_state" column that gets updated in place — that pattern invites R3
  violations (partial overwrite bugs) and makes order-independence hard to prove.

**Derived on every read (and on every write, to compute the outcome):**
`current_state`, `attrs`, `history`, `missing_milestones`, `rejected_events` —
all computed by `derive_serial_state()` from the full stored event set.

**Why this split:** recomputing from raw events is the only representation that
is *obviously* correct against §5.0 and trivially satisfies R2 (same set → same
function → same output, independent of insertion order). The cost is O(events
per serial) per request; acceptable because lifecycle event counts per serial
are small (single digits to low tens), unlike the hundreds-of-millions row count
across *all* serials (addressed separately in the README's indexing answer).

## 4. Build order (TDD — test written and failing before implementation, every step)

1. `derive_serial_state()` — pure function, no I/O. Tests first:
   - AC1 shape (duplicate event_id ignored)
   - AC3 shape (late event doesn't regress state/attrs)
   - AC4 shape (invalid transition rejected with reason)
   - §6 worked example (AC5), fed in multiple shuffled orders (AC2)
2. Storage layer (SQLite) — insert-with-uniqueness-constraint test, then wire to
   the pure function.
3. `POST /events` — single + batch, per-event outcome (`applied` /
   `duplicate` / `rejected`). Test AC1, AC4, batch handling.
4. `GET /serials/{serial_id}` — exact response shape test, 404 test, AC5/AC6
   field-by-field comparison against §6.
5. Concurrency (R5) — best-effort transaction/lock; test is optional (§9) and
   will be dropped first if time runs out.
6. React detail screen — state, milestone timeline, history, rejected events
   (AC6). No test framework setup unless time remains; manual verification
   against the running backend is the fallback.
7. `README.md` (run commands, R1–R5 explanation, scale/indexing answer — AC7,
   AC8) and `LLM-BRIEF.md`.

**Drop order if time runs short (first dropped → last):**
1. React styling polish (not scored).
2. Concurrency test (R5 write-safety itself is not dropped, only its test).
3. Batch-endpoint edge cases beyond the happy path.
4. Frontend entirely, if the backend + tests are not done by minute ~45 —
   backend correctness and tests outrank a UI per §10 scoring.

## 5. Tasks and subtasks created (reviewer visibility)

This is a plain summary for reviewers; completion tracking with checkboxes lives
in `AGENT_FILES/TASKS.md`.

- Analyze the brief, identify holes/ambiguities, and write `PLAN.md`.
- Test + implement `derive_serial_state()` pure function:
  - Validate idempotency (AC1)
  - Validate order independence (AC2)
  - Validate no regress for late events (AC3)
  - Validate invalid transitions are rejected (AC4)
  - Validate the §6 worked example (AC5)
- Set up the Python backend project structure and SQLite storage (`events` table with `event_id` uniqueness constraint).
- Test + implement `POST /events` for single and batch events, returning per-event outcomes (`applied` / `duplicate` / `rejected`).
- Test + implement `GET /serials/{serial_id}` with the exact response shape and `404` for unknown serials.
- Run the §6 worked example through multiple shuffled arrival orders to prove order independence.
- Implement the React serial detail screen (current state, milestone timeline, accepted history, rejected events with reasons).
- Write `README.md` with literal run/seed/test commands, R1–R5 enforcement explanation, and the scale/indexing answer.
- Write `LLM-BRIEF.md` from the prompt/response transcript in `AGENT_FILES/HANDOFF.md`.
- Optional post-timebox items: concurrency test, Docker compose, real search endpoint/screen, CI.

## 6. Holes found in the brief, and the interpretation chosen

- **`seq` field:** described as "monotonic per producer" but multiple producers
  exist and it is explicitly not globally ordered. §5.0's ordering rule uses only
  `(event_time, event_id)`. **Interpretation: `seq` is stored but never used for
  ordering or acceptance logic** — it's informational/audit-only.
- **Duplicate `event_id` with different payload:** not addressed. **Interpretation:**
  `event_id` is treated as immutable once stored; a second POST with the same
  `event_id` is always `duplicate` regardless of whether its body differs from
  the original (the uniqueness constraint enforces this at the DB level too).
- **Batch semantics:** unclear whether batch events are applied atomically as a
  set or independently. **Interpretation:** each event in a batch is evaluated
  independently and gets its own outcome; final derived state is still purely a
  function of the full stored set per §5.0, so batch vs. sequential singles
  produce identical end state either way.
- **Can a serial have zero history?** No — §5.0 says the first event in the
  sorted chain is always accepted, so any serial with ≥1 stored event has ≥1
  history entry. A serial that has never received any event simply doesn't
  exist (`GET` → 404).
- **"Two servers fed the same events in different orders must end up
  byte-for-byte identical":** taken literally to mean the derivation must be a
  pure function of the deduplicated set — this is the core design decision in
  §2 above, not an incidental detail.
- **Database choice vs. §4's "hundreds of millions of rows" scale question:**
  the exercise says database choice is free and unscored on engine, but the
  scale answer in the README is scored. **Interpretation:** pick the simplest
  engine for the 60-minute build (SQLite) and answer the scale question in
  README as a forward-looking design discussion, not as something implemented.
