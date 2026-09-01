"""Load demo data into a running tracker server."""

import httpx

EVENTS = [
    {"event_id": "E-01", "serial_id": "S-1", "state": "Created", "event_time": "2026-08-14T08:00:00Z", "seq": 1, "attrs": {"lot": "L-1"}},
    {"event_id": "E-04", "serial_id": "S-1", "state": "Received", "event_time": "2026-08-14T09:30:00Z", "seq": 2, "attrs": {"gln": "GLN-0"}},
    {"event_id": "E-02", "serial_id": "S-1", "state": "Received", "event_time": "2026-08-14T10:00:00Z", "seq": 3, "attrs": {"gln": "GLN-9"}},
    {"event_id": "E-03", "serial_id": "S-1", "state": "Shipped", "event_time": "2026-08-14T12:00:00Z", "seq": 4, "attrs": {"po": "PO-77"}},
    {"event_id": "E-05", "serial_id": "S-1", "state": "PACKING", "event_time": "2026-08-14T13:00:00Z", "seq": 5, "attrs": {}},
]


def main():
    try:
        r = httpx.post("http://localhost:8000/events", json=EVENTS)
        print("POST /events response:")
        print(r.json())
        print()
        g = httpx.get("http://localhost:8000/serials/S-1")
        print("GET /serials/S-1 response:")
        print(g.json())
    except httpx.ConnectError as exc:
        print("Could not connect to http://localhost:8000 — start the server first.")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
