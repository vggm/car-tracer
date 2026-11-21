import uuid

SCAN_TIMEOUT_MS = 90_000


def create_scan(conn, now_ms: int) -> str:
    scan_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO scan_requests(id, requested_at) VALUES (?, ?)", (scan_id, now_ms)
    )
    return scan_id


def pending_commands(conn, now_ms: int) -> list[dict]:
    rows = conn.execute(
        "SELECT id FROM scan_requests WHERE done_at IS NULL AND requested_at > ?"
        " ORDER BY requested_at",
        (now_ms - SCAN_TIMEOUT_MS,),
    ).fetchall()
    return [{"type": "read_dtc", "id": r[0]} for r in rows]


def open_scans(conn) -> list[tuple[str, int]]:
    rows = conn.execute(
        "SELECT id, requested_at FROM scan_requests WHERE done_at IS NULL"
        " ORDER BY requested_at"
    ).fetchall()
    return [(r[0], r[1]) for r in rows]


def scan_result(conn, scan_id: str) -> tuple[str, int] | None:
    rows = conn.execute(
        "SELECT json_extract(data, '$.event'), json_extract(data, '$.detail'), ts"
        " FROM records WHERE type = 'event'"
        " AND json_extract(data, '$.event') IN ('dtc_scan', 'dtc_scan_failed')"
        " ORDER BY ts"
    ).fetchall()
    for event, detail, ts in rows:
        if detail and detail.split(" ", 1)[0] == scan_id:
            return ("done" if event == "dtc_scan" else "failed", ts)
    return None


def close_scan(conn, scan_id: str, result: str, now_ms: int) -> None:
    conn.execute(
        "UPDATE scan_requests SET done_at = ?, result = ? WHERE id = ?",
        (now_ms, result, scan_id),
    )
