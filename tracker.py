"""Pure state-derivation logic for the idempotent serial tracker."""

VALID_TRANSITIONS = {
    "Created (Commissioned)": {"Received", "Decommissioned", "PACKING", "Shipped"},
    "Created": {"Received", "Decommissioned", "PACKING", "Shipped"},
    "Received": {"Decommissioned", "Shipped", "PACKING", "UPDATE_EVENT"},
    "PACKING": {"Shipped", "Decommissioned", "UPDATE_EVENT"},
    "Shipped": {"Decommissioned", "UPDATE_EVENT"},
    "UPDATE_EVENT": {"UPDATE_EVENT", "Decommissioned", "PACKING", "Shipped", "Received"},
    "Receipt Reversal": {"Received", "Decommissioned", "PACKING", "Shipped"},
    "Return Reversal": {"Decommissioned", "UPDATE_EVENT", "Received", "PACKING", "Shipped"},
    "Decommissioned": set(),
}

MILESTONE_STATES = ["Created", "Received", "PACKING", "Shipped"]


def _valid_transition(prev_state: str, next_state: str) -> bool:
    """Return True if next_state is a valid transition from prev_state."""
    if prev_state == next_state:
        return True
    return next_state in VALID_TRANSITIONS.get(prev_state, set())


def derive_serial_state(serial_id: str, events: list) -> dict | None:
    """Compute the deterministic serial-state document from a list of events.

    The events list may contain duplicates and may arrive in any order.
    The result is a pure function of the deduplicated event set.
    """
    if not events:
        return None

    # Deduplicate by event_id, then sort by (event_time, event_id).
    by_id = {ev["event_id"]: ev for ev in events}
    sorted_events = sorted(by_id.values(), key=lambda ev: (ev["event_time"], ev["event_id"]))

    accepted = []
    rejected = []

    for ev in sorted_events:
        if not accepted:
            accepted.append(ev)
            continue

        prev_state = accepted[-1]["state"]
        next_state = ev["state"]
        if _valid_transition(prev_state, next_state):
            accepted.append(ev)
        else:
            rejected.append(
                {
                    "event_id": ev["event_id"],
                    "state": ev["state"],
                    "event_time": ev["event_time"],
                    "reason": f"invalid transition {prev_state} -> {next_state}",
                }
            )

    # Merge attrs: for each key, the accepted event with the highest
    # (event_time, event_id) wins. Keys are never removed once set.
    attrs = {}
    for ev in accepted:
        for key, value in (ev.get("attrs") or {}).items():
            attrs[key] = value

    # Build history from accepted events (already sorted).
    history = [
        {"event_id": ev["event_id"], "state": ev["state"], "event_time": ev["event_time"]}
        for ev in accepted
    ]

    current_state = accepted[-1]["state"] if accepted else None

    # Milestones: Created counts for Created or Created (Commissioned).
    reached = set()
    for ev in accepted:
        if ev["state"] in ("Created", "Created (Commissioned)"):
            reached.add("Created")
        elif ev["state"] in MILESTONE_STATES:
            reached.add(ev["state"])
    missing_milestones = [m for m in MILESTONE_STATES if m not in reached]

    # Rejected events sorted deterministically by (event_time, event_id).
    rejected.sort(key=lambda ev: (ev["event_time"], ev["event_id"]))

    return {
        "serial_id": serial_id,
        "current_state": current_state,
        "attrs": attrs,
        "history": history,
        "missing_milestones": missing_milestones,
        "rejected_events": rejected,
    }
