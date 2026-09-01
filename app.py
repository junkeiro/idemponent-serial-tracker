"""FastAPI app for the idempotent serial tracker."""

import json
import os
import sqlite3
import threading
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from tracker import derive_serial_state

DB_PATH = os.environ.get("DATABASE_URL", "tracker.db")
_db = None
_write_lock = threading.Lock()

app = FastAPI()


class Event(BaseModel):
    event_id: str
    serial_id: str
    state: str
    event_time: str
    seq: int = 0
    attrs: dict = {}


def init_db(path: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or DB_PATH, check_same_thread=False)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            event_id TEXT PRIMARY KEY,
            serial_id TEXT NOT NULL,
            state TEXT NOT NULL,
            event_time TEXT NOT NULL,
            seq INTEGER,
            attrs TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_serial ON events(serial_id)")
    conn.commit()
    return conn


def get_db() -> sqlite3.Connection:
    global _db
    if _db is None:
        _db = init_db()
    return _db


# Initialise the database on import so the app is ready to run.
get_db()


def _events_for_serial(serial_id: str, conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT event_id, serial_id, state, event_time, seq, attrs "
        "FROM events WHERE serial_id = ? ORDER BY event_time, event_id",
        (serial_id,),
    ).fetchall()
    return [
        {
            "event_id": row[0],
            "serial_id": row[1],
            "state": row[2],
            "event_time": row[3],
            "seq": row[4],
            "attrs": json.loads(row[5]) if row[5] else {},
        }
        for row in rows
    ]


def _serial_outcome(serial_id: str, conn: sqlite3.Connection) -> dict:
    events = _events_for_serial(serial_id, conn)
    if not events:
        raise HTTPException(status_code=404, detail="serial not found")
    return derive_serial_state(serial_id, events)


@app.post("/events")
def post_events(payload: Event | list[Event] | dict | list[dict]) -> dict:
    """Accept one event or a batch and return a per-event outcome."""
    raw = payload if isinstance(payload, list) else [payload]
    events = [ev if isinstance(ev, dict) else ev.model_dump() for ev in raw]

    # Group by serial so we only recompute once per serial touched by the request.
    by_serial: dict[str, list[dict]] = {}
    for ev in events:
        by_serial.setdefault(ev["serial_id"], []).append(ev)

    results: list[dict[str, Any]] = []

    with _write_lock:
        conn = get_db()
        for serial_id, serial_events in by_serial.items():
            inserted_ids: set[str] = set()
            for ev in serial_events:
                cur = conn.execute(
                    """
                    INSERT OR IGNORE INTO events (event_id, serial_id, state, event_time, seq, attrs)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ev["event_id"],
                        serial_id,
                        ev["state"],
                        ev["event_time"],
                        ev.get("seq", 0),
                        json.dumps(ev.get("attrs") or {}),
                    ),
                )
                if cur.rowcount == 1:
                    inserted_ids.add(ev["event_id"])
            conn.commit()

            state = _serial_outcome(serial_id, conn)
            applied_ids = {h["event_id"] for h in state["history"]}
            rejected_by_id = {r["event_id"]: r["reason"] for r in state["rejected_events"]}

            for ev in serial_events:
                eid = ev["event_id"]
                if eid not in inserted_ids:
                    results.append({"event_id": eid, "outcome": "duplicate"})
                elif eid in applied_ids:
                    results.append({"event_id": eid, "outcome": "applied"})
                elif eid in rejected_by_id:
                    results.append(
                        {"event_id": eid, "outcome": "rejected", "reason": rejected_by_id[eid]}
                    )
                else:  # pragma: no cover
                    # Defensive: treat as applied if it was inserted and not rejected.
                    results.append({"event_id": eid, "outcome": "applied"})

    return {"results": results}


@app.get("/serials/{serial_id}")
def get_serial(serial_id: str) -> dict:
    """Return the current deterministic state document for a serial."""
    conn = get_db()
    return _serial_outcome(serial_id, conn)


# Serve the React detail view from the frontend directory.
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
