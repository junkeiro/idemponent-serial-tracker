# Project: Idempotent Serial Tracker

> Build a Python + React pharmaceutical serial-tracker that ingests out-of-order,
> duplicated, and partial lifecycle events and produces a deterministic current
> state per serial via `POST /events` and `GET /serials/{serial_id}`.

## Context files (read at session start)

Agent files live under **`AGENT_FILES/`**. Read whatever exists before starting work:

- **TASKS.md** — `AGENT_FILES/TASKS.md` (project-wide goals and steps)
- **HANDOFF.md** — `AGENT_FILES/HANDOFF.md`
- **MEMORY.md** — `AGENT_FILES/MEMORY.md`

The exercise brief is in the repo root as `idempotent-serial-tracker 1.md`.

## Behaviour

- Read the context files above from their actual paths before starting work.
- Update `AGENT_FILES/TASKS.md` for project-wide steps and backlog.
- Update `AGENT_FILES/HANDOFF.md` at the end of each working session **and** after each meaningful turn.
- **Keep a running log of every operator prompt and assistant response in `AGENT_FILES/HANDOFF.md`; this is the raw source for `LLM-BRIEF.md` and must persist across sessions. Record the local timestamp, elapsed time since the activity start (13:58 CST), and the AI model/assistant identifier used for each response.**
- **Do not run `git commit` or `git push` unless the operator uses explicit words such as "commit and push", "upload this to the server", or similar. Do not infer commit/push permission from general go-ahead wording.**
- Update `AGENT_FILES/MEMORY.md` only for decisions, constraints, or discoveries worth preserving.
- This project does **not** use Jira tracking; do not create `AGENT_FILES/JIRA/` or Jira files unless explicitly asked.
- Enforce the invariants in `idempotent-serial-tracker 1.md`:
  - **R1** idempotency,
  - **R2** order independence,
  - **R3** no overwrite / no regress,
  - **R4** invalid transitions recorded, not applied,
  - **R5** safe concurrent writes.
- Backend endpoints: `POST /events`, `GET /serials/{serial_id}`.
- Frontend: one serial detail screen showing state, milestone timeline, accepted history, and rejected events.
