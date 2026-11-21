import uuid

CLEAR_CONFIRM_MS = 300_000


def create_confirmation(conn, now_ms: int) -> str:
    confirmation_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO clear_confirmations(id, created_at) VALUES (?, ?)",
        (confirmation_id, now_ms),
    )
    return confirmation_id


def consume_confirmation(conn, confirmation_id: str, now_ms: int) -> bool:
    """True only if it exists, is unused and not expired; always marks it used."""
    cur = conn.execute(
        "UPDATE clear_confirmations SET used_at = ? WHERE id = ? AND used_at IS NULL"
        " AND created_at <= ?",
        (now_ms, confirmation_id, now_ms),
    )
    if cur.rowcount == 0:
        return False
    row = conn.execute(
        "SELECT created_at FROM clear_confirmations WHERE id = ?", (confirmation_id,)
    ).fetchone()
    return now_ms - row[0] <= CLEAR_CONFIRM_MS
