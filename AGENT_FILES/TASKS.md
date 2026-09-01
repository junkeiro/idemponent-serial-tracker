# Tasks

## Main goal

Build a Python + React serial-tracker that ingests out-of-order, duplicated, and
partial lifecycle events and produces a deterministic current state per serial.

## Method

**Strict TDD.** For every sub-task below: write the failing test first (mapped
to its AC), watch it fail, then implement the minimum to pass. No production
code without a preceding failing test, per operator instruction.

## Sub-tasks / steps (each graded against its AC — see PLAN.md §4 for order/drop order)

- [x] Analyze the brief, identify holes/ambiguities, and write `PLAN.md` (must be committed before first code commit — **committed**).
- [x] Test + implement `derive_serial_state()` pure function — covers AC1, AC2, AC3, AC4, AC5 at the unit level before any HTTP layer exists.
- [x] Set up Python backend project structure and SQLite storage (events table, `event_id` uniqueness constraint) — test the uniqueness constraint (AC1) before wiring.
- [x] Test + implement `POST /events` (single + batch) — per-event outcome `applied`/`duplicate`/`rejected`. Covers AC1, AC4.
- [x] Test + implement `GET /serials/{serial_id}` — exact response shape, 404 for unknown serial. Covers AC5, AC6 (backend half).
- [x] Test the §6 worked example fed in multiple shuffled arrival orders — covers AC2 + AC5 together (this is the primary regression test).
- [x] Implement React serial detail screen (state, milestone timeline, history, rejected events with reasons) — covers AC6 (frontend half). Verify manually against running backend if no frontend test framework is set up in time.
- [x] Create `seed.py` for demo data and manually verify app starts/seed loads/frontend serves.
- [x] Write `README.md`: literal run/seed/test commands (AC7), R1–R5 enforcement explanation, and the scale/indexing answer (AC8).
- [x] Write `LLM-BRIEF.md` from the running log in `AGENT_FILES/HANDOFF.md` — prompts, corrections, rejections.
- [ ] (Optional post-timebox only, marked in separate commits) Concurrency test, Docker compose, real search endpoint/screen, CI.

## Grading checklist (map before calling anything "done")

| AC | Covered by | Status |
|----|-----------|--------|
| AC1 idempotency | `derive_serial_state` unit test + `POST /events` duplicate test + SQLite unique constraint | passing |
| AC2 order independence | shuffled-order §6 test (unit + API) | passing |
| AC3 no regress | `derive_serial_state` unit test (late `Received`) | passing |
| AC4 invalid transition rejected | `derive_serial_state` unit test + `POST /events` test | passing |
| AC5 §6 worked example exact match | shuffled-order §6 test | passing |
| AC6 frontend milestone/rejected view | `frontend/index.html` React detail screen, manually verified | passing |
| AC7 runs in ≤2 commands, seed in 1, tests in 1 | README literal commands, verified by running them | passing |
| AC8 scale/index answer | README section | passing |

## Completed

- [x] Read `idempotent-serial-tracker 1.md`, drafted `PLAN.md` with invariant placement, data model, build order, drop order, and brief holes/interpretations.
- [x] Implemented `derive_serial_state()` and unit tests (10 passing).
- [x] Implemented SQLite storage, `POST /events`, `GET /serials/{serial_id}`, and endpoint tests (8 additional passing, 18 total).
- [x] Built React detail view (`frontend/index.html`) and `seed.py`; manually verified app starts and seed loads.
