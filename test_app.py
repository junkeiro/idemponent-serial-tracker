"""Tests for the FastAPI HTTP endpoints."""

import os

os.environ.setdefault("DATABASE_URL", ":memory:")

import pytest
from fastapi.testclient import TestClient

import app as app_module

client = TestClient(app_module.app)


@pytest.fixture(autouse=True)
def fresh_db():
    """Reset the in-memory database before every test."""
    if app_module._db is not None:
        try:
            app_module._db.close()
        except Exception:
            pass
    app_module._db = None
    app_module.get_db()


def _event(event_id, serial_id, state, event_time, attrs=None, seq=1):
    return {
        "event_id": event_id,
        "serial_id": serial_id,
        "state": state,
        "event_time": event_time,
        "seq": seq,
        "attrs": attrs or {},
    }


def test_get_unknown_serial():
    response = client.get("/serials/UNKNOWN")
    assert response.status_code == 404


def test_post_single_event_and_get():
    event = _event("E-01", "S-1", "Created", "2026-08-14T08:00:00Z", {"lot": "L-1"})
    post = client.post("/events", json=event)
    assert post.status_code == 200
    assert post.json() == {"results": [{"event_id": "E-01", "outcome": "applied"}]}

    get = client.get("/serials/S-1")
    assert get.status_code == 200
    body = get.json()
    assert body["serial_id"] == "S-1"
    assert body["current_state"] == "Created"
    assert body["attrs"] == {"lot": "L-1"}
    assert body["missing_milestones"] == ["Received", "PACKING", "Shipped"]


def test_post_duplicate_event():
    """AC1 via API: re-posting the same event_id is a duplicate and leaves state unchanged."""
    event = _event("E-01", "S-1", "Created", "2026-08-14T08:00:00Z", {"lot": "L-1"})
    first = client.post("/events", json=event)
    second = client.post("/events", json=event)
    assert second.status_code == 200
    assert second.json() == {"results": [{"event_id": "E-01", "outcome": "duplicate"}]}

    get = client.get("/serials/S-1")
    body = get.json()
    assert body["current_state"] == "Created"
    assert body["history"] == [
        {"event_id": "E-01", "state": "Created", "event_time": "2026-08-14T08:00:00Z"}
    ]


def test_post_batch():
    events = [
        _event("E-01", "S-1", "Created", "2026-08-14T08:00:00Z", {"lot": "L-1"}),
        _event("E-02", "S-1", "Received", "2026-08-14T10:00:00Z", {"gln": "GLN-9"}),
    ]
    response = client.post("/events", json=events)
    assert response.status_code == 200
    assert response.json()["results"] == [
        {"event_id": "E-01", "outcome": "applied"},
        {"event_id": "E-02", "outcome": "applied"},
    ]


def test_invalid_transition_after_decommissioned():
    """AC4 via API: events after Decommissioned are rejected with a reason."""
    events = [
        _event("E-01", "S-1", "Created", "2026-08-14T08:00:00Z"),
        _event("E-02", "S-1", "Decommissioned", "2026-08-14T09:00:00Z"),
        _event("E-03", "S-1", "Shipped", "2026-08-14T10:00:00Z"),
    ]
    response = client.post("/events", json=events)
    assert response.status_code == 200
    results = response.json()["results"]
    assert results == [
        {"event_id": "E-01", "outcome": "applied"},
        {"event_id": "E-02", "outcome": "applied"},
        {"event_id": "E-03", "outcome": "rejected", "reason": "invalid transition Decommissioned -> Shipped"},
    ]

    get = client.get("/serials/S-1")
    body = get.json()
    assert body["current_state"] == "Decommissioned"
    assert len(body["rejected_events"]) == 1


@pytest.mark.parametrize("order", [
    ["E-03", "E-01", "E-03", "E-02", "E-04", "E-05"],
    ["E-01", "E-02", "E-03", "E-04", "E-05", "E-03"],
    ["E-05", "E-04", "E-03", "E-02", "E-01", "E-03"],
])
def test_section_six_in_any_arrival_order(order):
    """AC2 + AC5 via API: §6 example in multiple orders yields identical output."""
    event_map = {
        "E-01": _event("E-01", "S-1", "Created", "2026-08-14T08:00:00Z", {"lot": "L-1"}),
        "E-02": _event("E-02", "S-1", "Received", "2026-08-14T10:00:00Z", {"gln": "GLN-9"}),
        "E-03": _event("E-03", "S-1", "Shipped", "2026-08-14T12:00:00Z", {"po": "PO-77"}),
        "E-04": _event("E-04", "S-1", "Received", "2026-08-14T09:30:00Z", {"gln": "GLN-0"}),
        "E-05": _event("E-05", "S-1", "PACKING", "2026-08-14T13:00:00Z"),
    }
    events = [event_map[eid] for eid in order]
    response = client.post("/events", json=events)
    assert response.status_code == 200

    get = client.get("/serials/S-1")
    assert get.status_code == 200
    body = get.json()
    assert body["current_state"] == "Shipped"
    assert body["attrs"] == {"lot": "L-1", "gln": "GLN-9", "po": "PO-77"}
    assert [h["event_id"] for h in body["history"]] == ["E-01", "E-04", "E-02", "E-03"]
    assert body["missing_milestones"] == ["PACKING"]
    assert len(body["rejected_events"]) == 1
    assert body["rejected_events"][0]["event_id"] == "E-05"
    assert "invalid transition Shipped -> PACKING" in body["rejected_events"][0]["reason"]
