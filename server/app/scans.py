import uuid

SCAN_TIMEOUT_MS = 90_000


_FAMILY = {
    "read_dtc": ("dtc_scan", "dtc_scan_failed"),
    "clear_dtc": ("dtc_clear", "dtc_clear_failed"),
}


def create_scan(conn, now_ms: int, kind: str = "read_dtc") -> str:
    scan_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO scan_requests(id, requested_at, kind) VALUES (?, ?, ?)",
        (scan_id, now_ms, kind),
    )
    return scan_id


def pending_commands(conn, now_ms: int) -> list[dict]:
    rows = conn.execute(
        "SELECT id, kind FROM scan_requests WHERE done_at IS NULL AND requested_at > ?"
        " ORDER BY requested_at",
        (now_ms - SCAN_TIMEOUT_MS,),
    ).fetchall()
    return [{"type": r[1], "id": r[0]} for r in rows]


def open_scans(conn) -> list[tuple[str, int, str]]:
    rows = conn.execute(
        "SELECT id, requested_at, kind FROM scan_requests WHERE done_at IS NULL"
        " ORDER BY requested_at"
    ).fetchall()
    return [(r[0], r[1], r[2]) for r in rows]


def _find_event(conn, scan_id: str) -> tuple[str, str, int, bool] | None:
    """(event, detail, ts, ok) of the first event of the request's family naming it."""
    row = conn.execute(
        "SELECT kind FROM scan_requests WHERE id = ?", (scan_id,)
    ).fetchone()
    # no request row: fall back to the original read family
    ok_event, failed_event = _FAMILY.get(row[0] if row else "read_dtc", (None, None))
    if ok_event is None:
        return None
    rows = conn.execute(
        "SELECT json_extract(data, '$.event'), json_extract(data, '$.detail'), ts"
        " FROM records WHERE type = 'event'"
        " AND json_extract(data, '$.event') IN (?, ?)"
        " ORDER BY ts",
        (ok_event, failed_event),
    ).fetchall()
    for event, detail, ts in rows:
        if detail and detail.split(" ", 1)[0] == scan_id:
            return event, detail, ts, event == ok_event
    return None


def scan_result(conn, scan_id: str) -> tuple[str, int] | None:
    found = _find_event(conn, scan_id)
    if found is None:
        return None
    _event, _detail, ts, ok = found
    return ("done" if ok else "failed", ts)


def failure_reason(conn, scan_id: str) -> str | None:
    found = _find_event(conn, scan_id)
    if found is None or found[3]:
        return None
    parts = found[1].split(" ", 1)
    return parts[1] if len(parts) > 1 and parts[1] else None


def close_scan(conn, scan_id: str, result: str, now_ms: int) -> None:
    conn.execute(
        "UPDATE scan_requests SET done_at = ?, result = ? WHERE id = ?",
        (now_ms, result, scan_id),
    )
