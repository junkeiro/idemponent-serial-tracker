"""Tests for the pure state-derivation logic."""

import pytest
from tracker import derive_serial_state


def _event(event_id, serial_id, state, event_time, attrs=None, seq=1):
    return {
        "event_id": event_id,
        "serial_id": serial_id,
        "state": state,
        "event_time": event_time,
        "seq": seq,
        "attrs": attrs or {},
    }


def test_empty_event_list():
    """A serial with no events has no state."""
    assert derive_serial_state("S-1", []) is None


def test_single_event_accepted():
    """The first event for a serial is always accepted."""
    events = [_event("E-01", "S-1", "Created", "2026-08-14T08:00:00Z", {"lot": "L-1"})]
    result = derive_serial_state("S-1", events)
    assert result["current_state"] == "Created"
    assert result["attrs"] == {"lot": "L-1"}
    assert result["history"] == [
        {"event_id": "E-01", "state": "Created", "event_time": "2026-08-14T08:00:00Z"}
    ]
    assert result["missing_milestones"] == ["Received", "PACKING", "Shipped"]
    assert result["rejected_events"] == []


def test_idempotency_duplicate_event_id():
    """AC1: duplicate event_id produces the same result as a single event."""
    event = _event("E-01", "S-1", "Created", "2026-08-14T08:00:00Z", {"lot": "L-1"})
    single = derive_serial_state("S-1", [event])
    duplicate = derive_serial_state("S-1", [event, event])
    assert duplicate == single


def test_order_independence():
    """AC2: shuffled arrival order yields identical state."""
    events = [
        _event("E-03", "S-1", "Shipped", "2026-08-14T12:00:00Z", {"po": "PO-77"}),
        _event("E-01", "S-1", "Created", "2026-08-14T08:00:00Z", {"lot": "L-1"}),
        _event("E-02", "S-1", "Received", "2026-08-14T10:00:00Z", {"gln": "GLN-9"}),
        _event("E-04", "S-1", "Received", "2026-08-14T09:30:00Z", {"gln": "GLN-0"}),
    ]
    result_a = derive_serial_state("S-1", events)
    shuffled = list(events)
    shuffled.reverse()
    result_b = derive_serial_state("S-1", shuffled)
    assert result_a == result_b


def test_no_regress_late_received_does_not_overwrite():
    """AC3: an older Received event carrying lot L0 does not overwrite lot L1 or remove po."""
    events = [
        _event("E-01", "S-1", "Created", "2026-08-14T08:00:00Z", {"lot": "L-1"}),
        _event("E-02", "S-1", "Received", "2026-08-14T10:00:00Z", {"lot": "L-1"}),
        _event("E-03", "S-1", "Shipped", "2026-08-14T12:00:00Z", {"po": "P1"}),
        _event("E-04", "S-1", "Received", "2026-08-14T09:30:00Z", {"lot": "L0"}),
    ]
    result = derive_serial_state("S-1", events)
    assert result["current_state"] == "Shipped"
    assert result["attrs"] == {"lot": "L-1", "po": "P1"}


def test_invalid_transition_after_decommissioned():
    """AC4: events after Decommissioned are rejected."""
    events = [
        _event("E-01", "S-1", "Created", "2026-08-14T08:00:00Z"),
        _event("E-02", "S-1", "Decommissioned", "2026-08-14T09:00:00Z"),
        _event("E-03", "S-1", "Shipped", "2026-08-14T10:00:00Z"),
    ]
    result = derive_serial_state("S-1", events)
    assert result["current_state"] == "Decommissioned"
    assert len(result["rejected_events"]) == 1
    assert result["rejected_events"][0]["event_id"] == "E-03"
    assert "invalid transition Decommissioned -> Shipped" in result["rejected_events"][0]["reason"]


def test_section_six_worked_example():
    """AC5: the six-event worked example matches the expected document."""
    events = [
        _event("E-03", "S-1", "Shipped", "2026-08-14T12:00:00Z", {"po": "PO-77"}),
        _event("E-01", "S-1", "Created", "2026-08-14T08:00:00Z", {"lot": "L-1"}),
        _event("E-03", "S-1", "Shipped", "2026-08-14T12:00:00Z", {"po": "PO-77"}),
        _event("E-02", "S-1", "Received", "2026-08-14T10:00:00Z", {"gln": "GLN-9"}),
        _event("E-04", "S-1", "Received", "2026-08-14T09:30:00Z", {"gln": "GLN-0"}),
        _event("E-05", "S-1", "PACKING", "2026-08-14T13:00:00Z"),
    ]
    result = derive_serial_state("S-1", events)
    assert result["serial_id"] == "S-1"
    assert result["current_state"] == "Shipped"
    assert result["attrs"] == {"lot": "L-1", "gln": "GLN-9", "po": "PO-77"}
    assert result["history"] == [
        {"event_id": "E-01", "state": "Created", "event_time": "2026-08-14T08:00:00Z"},
        {"event_id": "E-04", "state": "Received", "event_time": "2026-08-14T09:30:00Z"},
        {"event_id": "E-02", "state": "Received", "event_time": "2026-08-14T10:00:00Z"},
        {"event_id": "E-03", "state": "Shipped", "event_time": "2026-08-14T12:00:00Z"},
    ]
    assert result["missing_milestones"] == ["PACKING"]
    assert result["rejected_events"] == [
        {
            "event_id": "E-05",
            "state": "PACKING",
            "event_time": "2026-08-14T13:00:00Z",
            "reason": "invalid transition Shipped -> PACKING",
        }
    ]


@pytest.mark.parametrize("order", [
    ["E-03", "E-01", "E-03", "E-02", "E-04", "E-05"],
    ["E-01", "E-02", "E-03", "E-04", "E-05", "E-03"],
    ["E-05", "E-04", "E-03", "E-02", "E-01", "E-03"],
])
def test_section_six_in_any_arrival_order(order):
    """AC2+AC5: §6 example fed in multiple orders yields identical output."""
    event_map = {
        "E-01": _event("E-01", "S-1", "Created", "2026-08-14T08:00:00Z", {"lot": "L-1"}),
        "E-02": _event("E-02", "S-1", "Received", "2026-08-14T10:00:00Z", {"gln": "GLN-9"}),
        "E-03": _event("E-03", "S-1", "Shipped", "2026-08-14T12:00:00Z", {"po": "PO-77"}),
        "E-04": _event("E-04", "S-1", "Received", "2026-08-14T09:30:00Z", {"gln": "GLN-0"}),
        "E-05": _event("E-05", "S-1", "PACKING", "2026-08-14T13:00:00Z"),
    }
    events = [event_map[eid] for eid in order]
    result = derive_serial_state("S-1", events)
    assert result["current_state"] == "Shipped"
    assert result["attrs"] == {"lot": "L-1", "gln": "GLN-9", "po": "PO-77"}
    assert [h["event_id"] for h in result["history"]] == ["E-01", "E-04", "E-02", "E-03"]
    assert result["missing_milestones"] == ["PACKING"]
    assert len(result["rejected_events"]) == 1
    assert result["rejected_events"][0]["event_id"] == "E-05"
