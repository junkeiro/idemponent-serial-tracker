# Exercise — Idempotent Serial Tracker

**Timebox: 60 minutes.** Python backend + React frontend + a database of your choice.

At the end of the hour we expect a **running application with tests**, plus the two documents described in §8. Not a sketch, not a branch that almost works.

## What this exercise measures

Not typing speed. Three things:

1. **Analysis** — this brief is deliberately incomplete. Can you find the holes and decide what to do about them before writing code?
2. **Planning** — can you turn an ambiguous problem into a sequence you can actually finish in the time you have, including what you deliberately drop?
3. **Driving an LLM, and not trusting it** — you are expected to use an assistant. The interesting question is whether you can tell when it hands you something that looks right and is wrong.

Use any AI assistant you want. That is the point, not a concession. But you will be asked to explain and defend every line you ship.

---

## 1. How this exercise runs

| Phase | Budget | Output |
| --- | --- | --- |
| Analyze and plan | ~10 min | `PLAN.md`, **committed before your first code commit** |
| Build and test | ~35 min | Working app + tests, committed as you go |
| Run, verify, write up | ~10 min | `README.md`, `LLM-BRIEF.md` |

The commit order matters and we read it. `PLAN.md` landing after the code reads as a plan written to fit what already got built.

Stop at sixty minutes. Anything after that goes in a separate commit clearly marked as post-timebox — see §9.

---

## 2. Context

You are building a tracker for serialized pharmaceutical units. Each unit has a unique serial and moves through a lifecycle: it is created, received into a warehouse, packed, shipped, and sometimes decommissioned or reversed.

State changes reach you as **events on a queue**, and the queue gives you no guarantees:

- Events arrive **out of order**. A `Shipped` event can land before the `Received` event that logically precedes it.
- Events are **duplicated**. The same event can be delivered two, three, or twenty times.
- Whole batches get **replayed** after an incident — hours of traffic re-delivered from the beginning.
- Events carry **partial attributes**. One event knows the lot, another knows the purchase order, neither knows both.

Nobody upstream will fix this for you. The consumer has to be correct anyway.

All data in this exercise is synthetic. Invent your own serials, lots and locations.

---

## 3. The data

### Event

```json
{
  "event_id": "5f1c0a9e-2d4b-4f0a-9c1e-7b3a8d21e004",
  "serial_id": "01003600012345212ABC000001",
  "state": "Received",
  "event_time": "2026-08-14T09:31:22.481Z",
  "seq": 41207,
  "attrs": {
    "lot": "L2291",
    "po": "4500881230",
    "gln": "0360001234567"
  }
}
```

- `event_id` — globally unique, stable across redeliveries of the same event.
- `serial_id` — the unit this event is about.
- `state` — one of the nine states below.
- `event_time` — when the event happened upstream. **Two events can share the same `event_time`.**
- `seq` — a counter that is monotonic *per producer*, but there are several producers. Do not assume it is globally ordered.
- `attrs` — a partial bag of attributes. Keys vary between events.

### States

```
Created (Commissioned)
Created
Received
PACKING
Shipped
Decommissioned
UPDATE_EVENT
Receipt Reversal
Return Reversal
```

### Valid transitions

| From | To |
| --- | --- |
| `Created (Commissioned)` | `Received`, `Decommissioned`, `PACKING`, `Shipped` |
| `Created` | `Received`, `Decommissioned`, `PACKING`, `Shipped` |
| `Received` | `Decommissioned`, `Shipped`, `PACKING`, `UPDATE_EVENT` |
| `PACKING` | `Shipped`, `Decommissioned`, `UPDATE_EVENT` |
| `Shipped` | `Decommissioned`, `UPDATE_EVENT` |
| `UPDATE_EVENT` | `UPDATE_EVENT`, `Decommissioned`, `PACKING`, `Shipped`, `Received` |
| `Receipt Reversal` | `Received`, `Decommissioned`, `PACKING`, `Shipped` |
| `Return Reversal` | `Decommissioned`, `UPDATE_EVENT`, `Received`, `PACKING`, `Shipped` |
| `Decommissioned` | — (terminal) |

A transition from a state to **itself** is always valid.

### Milestones

The expected happy path is:

```
Created → Received → PACKING → Shipped
```

A serial that has not reached one of these is *missing* that milestone. The `Created` milestone is satisfied by either `Created` or `Created (Commissioned)`; the other three only by their exact state. A milestone counts as reached if the state appears anywhere in the accepted history, not only as the current state — a serial in `Shipped` that passed through `Received` has reached `Received`.

---

## 4. What to build

Python and React are fixed. Everything you choose inside them is free: any web framework, any libraries, any database.

### Backend — two endpoints

**`POST /events`** — accepts one event or a batch. This is the core of the exercise. Returns a per-event outcome:

```json
{ "results": [
    { "event_id": "…", "outcome": "applied" },
    { "event_id": "…", "outcome": "duplicate" },
    { "event_id": "…", "outcome": "rejected", "reason": "invalid transition Shipped -> Received" }
] }
```

**`GET /serials/{serial_id}`** — the current picture of one unit. **Match this shape exactly**; it is compared field by field.

```json
{
  "serial_id": "S-1",
  "current_state": "Shipped",
  "attrs": { "lot": "L-1", "gln": "GLN-9", "po": "PO-77" },
  "history": [
    { "event_id": "E-01", "state": "Created",  "event_time": "2026-08-14T08:00:00Z" },
    { "event_id": "E-02", "state": "Received", "event_time": "2026-08-14T10:00:00Z" }
  ],
  "missing_milestones": ["PACKING"],
  "rejected_events": [
    { "event_id": "E-05", "state": "PACKING", "event_time": "2026-08-14T13:00:00Z",
      "reason": "invalid transition Shipped -> PACKING" }
  ]
}
```

`history` is ordered by `(event_time, event_id)` ascending. `reason` is free text — read by a human, not compared. Unknown serial returns `404`.

### Frontend — one screen

A detail view for one serial: current state, a timeline showing which milestones are done and which are missing, the accepted history, and the rejected events with their reasons. Plain CSS is fine. We are not scoring how it looks.

### Search — a written answer, not code

Do **not** build a search endpoint. Instead, answer this in your `README.md`:

> This collection eventually holds hundreds of millions of rows. Users need to filter by lot, by purchase order and by current state, paginated. Which indexes would you create, what would each query look like, and what would you refuse to do because it does not survive at that size?

We are looking for the reasoning, not the implementation. If you want to build it too, that is §9.

### Database

Your choice — SQLite, PostgreSQL, MongoDB, anything, including in-process. Nothing here requires Docker. We score how you shape the write, not the engine.

---

## 5. The rules

### 5.0 — How the current state is computed

This is the definition everything else rests on. Follow it literally; it is what makes a single correct answer exist.

> Take every event received for a serial, deduplicated by `event_id`, and sort it by `(event_time, event_id)` ascending. Walk that sorted chain:
>
> - The **first** event in the chain is always accepted, whatever its state.
> - Each following event is **accepted** if its state is a valid transition from the state of the previous *accepted* event (a transition to the same state is valid). Otherwise it is **rejected** and stored in `rejected_events` with a reason — it does not become the previous state for the next step.
> - `current_state` is the state of the last accepted event in the chain.
> - `attrs` is the merge of the accepted events' `attrs`, key by key: for each key, the value from the accepted event with the highest `(event_time, event_id)` wins. A key that no accepted event sets is absent. **A key is never removed once set.**
>
> An event that arrives late is inserted into the chain at its `event_time`, and the chain is evaluated from that definition — not from the order in which the events reached your API. Two servers fed the same events in different orders must end up byte-for-byte identical.

You do not have to literally recompute the whole chain on every write — that is one valid implementation, and there are cheaper ones. You have to produce the result this definition specifies.

### 5.1 — The invariants

**R1 — Idempotency.** Applying the same `event_id` any number of times has the same effect as applying it once. No duplicated history entries. A replay of yesterday's traffic is a no-op.

**R2 — Order independence.** Given the same set of events, the final stored document is identical no matter what order they arrive in.

**R3 — Never overwrite, never regress.** An old event arriving late does not move the unit backwards and does not blank out attributes a newer event already set. A late event carrying `lot` but not `po` must not erase `po`.

**R4 — Invalid transitions are recorded, not applied.** They do not change `current_state`; they are stored with a reason so someone can audit what upstream sent. `Decommissioned` accepts nothing further.

**R5 — Concurrency.** Two requests carrying events for the same serial can be processed at the same time. Neither may be silently lost. Read-modify-write without protection fails this — use a conditional update, an optimistic version, or a transaction. A test for this is optional (§9); getting the write right is not.

---

## 6. Worked example

One serial, six POSTs, in this arrival order. The arrival order is deliberately wrong.

| # | `event_id` | `state` | `event_time` | `attrs` | outcome |
|---|---|---|---|---|---|
| 1 | `E-03` | `Shipped` | `12:00:00Z` | `{"po": "PO-77"}` | `applied` |
| 2 | `E-01` | `Created` | `08:00:00Z` | `{"lot": "L-1"}` | `applied` |
| 3 | `E-03` | `Shipped` | `12:00:00Z` | `{"po": "PO-77"}` | `duplicate` |
| 4 | `E-02` | `Received` | `10:00:00Z` | `{"gln": "GLN-9"}` | `applied` |
| 5 | `E-04` | `Received` | `09:30:00Z` | `{"gln": "GLN-0"}` | `applied` |
| 6 | `E-05` | `PACKING` | `13:00:00Z` | `{}` | `rejected` |

All times are `2026-08-14`. The sorted chain is `E-01 (08:00) → E-04 (09:30) → E-02 (10:00) → E-03 (12:00)`: `Created → Received` is valid, `Received → Received` is valid, `Received → Shipped` is valid. `E-05` asks for `Shipped → PACKING`, which the table forbids.

After all six POSTs, `GET /serials/S-1` must return:

```json
{
  "serial_id": "S-1",
  "current_state": "Shipped",
  "attrs": { "lot": "L-1", "gln": "GLN-9", "po": "PO-77" },
  "history": [
    { "event_id": "E-01", "state": "Created",  "event_time": "2026-08-14T08:00:00Z" },
    { "event_id": "E-04", "state": "Received", "event_time": "2026-08-14T09:30:00Z" },
    { "event_id": "E-02", "state": "Received", "event_time": "2026-08-14T10:00:00Z" },
    { "event_id": "E-03", "state": "Shipped",  "event_time": "2026-08-14T12:00:00Z" }
  ],
  "missing_milestones": ["PACKING"],
  "rejected_events": [
    { "event_id": "E-05", "state": "PACKING", "event_time": "2026-08-14T13:00:00Z",
      "reason": "invalid transition Shipped -> PACKING" }
  ]
}
```

Three things to check yourself against:

- `gln` is `GLN-9`, not `GLN-0`. `E-04` arrived after `E-02` but happened *before* it, so it does not overwrite. That is R3.
- `E-04` is still in `history`, in its chronological position — arriving late is not the same as being wrong.
- Feed the same six events in any other order and you get this exact document back.

---

## 7. Acceptance criteria

Write these as tests. AC1–AC5 are mandatory.

**AC1 (R1)** — *Given* an event already applied, *when* the same `event_id` is POSTed again, *then* the outcome is `duplicate` and `history`, `attrs` and `current_state` are unchanged.

**AC2 (R2)** — *Given* a set of events for one serial, *when* the set is loaded into two empty databases in two different orders, *then* both hold identical `current_state`, `attrs` and `history`.

**AC3 (R3)** — *Given* a serial in `Shipped` with `attrs` `{lot: "L1", po: "P1"}`, *when* an older `Received` event carrying `{lot: "L0"}` arrives, *then* `current_state` stays `Shipped`, `lot` stays `L1`, and `po` is still there.

**AC4 (R4)** — *Given* a serial in `Decommissioned`, *when* a `Shipped` event arrives, *then* the outcome is `rejected` with a reason, `current_state` is unchanged, and the event appears in `rejected_events`.

**AC5 (§6)** — *Given* the six events of §6 in any arrival order, *when* `GET /serials/S-1` is called, *then* the response equals the document in §6 field by field (`reason` text excluded).

**AC6 (front)** — *Given* a serial that reached `Received` but never `PACKING` or `Shipped`, *when* the detail screen is opened, *then* `Created` and `Received` show as done, `PACKING` and `Shipped` as missing, and any rejected events are visible with their reasons.

**AC7 (it runs)** — *Given* a clean clone, *when* the `README.md` instructions are followed, *then* the app starts in **at most two commands**, demo data loads in **one**, and the tests run in **one**. State those commands literally.

**AC8 (scale)** — *Given* the question in §4, *when* the `README.md` is read, *then* it names the indexes, the shape of each query, and at least one thing you would refuse to do at that size.

---

## 8. What you deliver

A git repository — we read the commit history — containing:

**`PLAN.md`** — committed *before* your first code commit.

- What you understood the problem to be, in your own words.
- The invariant you decided to protect, and where in the system you decided to enforce it.
- Your data model: what you store per serial, what you derive on read, and why that split.
- The order you planned to build in, and what you planned to drop if you ran out of time.
- **The holes you found in this brief**, and the interpretation you chose for each. This brief is incomplete on purpose. Finding that out at minute 45 is the failure mode we are looking for.

**`LLM-BRIEF.md`** — what you asked your assistant.

- The initial instruction you gave it, verbatim.
- How you split the work into successive asks, rather than one big "build this".
- **Where it got something wrong, and what you said to correct it.** This is the part we read most closely.
- What you rejected outright, and why.

A `LLM-BRIEF.md` with no corrections in it means one of two things: you did not check its output, or you are polishing the story. Both are information.

**`README.md`** — how to run it (the literal commands from AC7), which database and why, how you enforce R1–R5, your answer to the scale question in §4, what you did not build, and anything you would push back on if this were a real ticket.

**The code and the tests.** Backend, frontend, and the tests for AC1–AC5.

---

## 9. If you finish early

Extras, most valuable first. Two rules: put them in commits clearly marked as post-timebox, and **an extra never covers a hole in §4 or §7**. An app that starts with `python main.py` and passes AC1–AC5 beats a beautifully containerized one that does not.

1. **`docker compose up`** brings up the whole thing, database included, in one command.
2. **The search endpoint for real** — a generator that loads data at volume, the indexes from your §4 answer, and a **measurement**. Not a claim that it is fast: a number, and how you got it.
3. **A concurrency test for R5** — N simultaneous POSTs for the same serial, nothing lost.
4. **The search screen**, with server-side pagination.
5. **CI** that runs the tests.
6. **Whatever you think we should have asked for and did not.** This one interests us most.

---

## 10. What we evaluate

**We score:**

- Correctness under messy input — duplicates, reordering, late arrivals, replays.
- The quality of `PLAN.md`: whether the holes you found are real ones, and whether the plan matches what you actually built.
- How you drove the assistant, and what you caught it doing wrong.
- Where you put the invariant. A rule enforced in one place beats the same rule repeated in five.
- Whether the write is safe when two things happen at once.
- Tests that pin down the rules rather than restate the code.
- The reasoning about what you did **not** build. A stated gap is a decision; an unstated one is an oversight.

**We do not score:**

- Visual design, CSS frameworks, animations.
- Authentication, authorization, deployment.
- Completeness for its own sake. A correct half beats a complete-but-fragile whole.
- Which database, Python web framework or React libraries you picked — those are free choices. The language and the UI library are not: a submission that is not Python + React is not evaluated.

---

## 11. Ground rules

- Use any library, framework, documentation or AI assistant you want. You will be asked to explain and defend every line you ship.
- Seed your own data. A small generator that emits shuffled, duplicated events is a good use of five minutes.
- Commit as you go, in the order you actually worked.
- Stop at sixty minutes for the core. Extras go in marked commits afterwards.

Expect a follow-up conversation where we hand you a new event ordering and ask what your system does with it.
