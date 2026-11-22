import json
import sqlite3
import threading

from app.contract import Record

SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
  id          TEXT PRIMARY KEY,
  device_id   TEXT NOT NULL,
  session_id  TEXT NOT NULL,
  seq         INTEGER NOT NULL,
  ts          INTEGER NOT NULL,
  type        TEXT NOT NULL,
  data        TEXT NOT NULL,
  received_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS records_type_ts ON records(type, ts);
CREATE INDEX IF NOT EXISTS records_session ON records(session_id, seq);
CREATE INDEX IF NOT EXISTS records_session_ts ON records(session_id, ts);
CREATE TABLE IF NOT EXISTS scan_requests (
  id           TEXT PRIMARY KEY,
  requested_at INTEGER NOT NULL,
  done_at      INTEGER,
  result       TEXT
);
CREATE TABLE IF NOT EXISTS clear_confirmations (
  id         TEXT PRIMARY KEY,
  created_at INTEGER NOT NULL,
  used_at    INTEGER
);
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);
"""


SCHEMA_VERSION = 2


def _migrate(conn: sqlite3.Connection) -> None:
    cols = [r[1] for r in conn.execute("PRAGMA table_info(scan_requests)")]
    if "kind" not in cols:
        try:
            conn.execute(
                "ALTER TABLE scan_requests ADD COLUMN kind TEXT NOT NULL DEFAULT 'read_dtc'"
            )
        except sqlite3.OperationalError:
            # another process (api / bot) added it first
            if "kind" not in [r[1] for r in conn.execute("PRAGMA table_info(scan_requests)")]:
                raise
    if conn.execute("SELECT count(*) FROM schema_version").fetchone()[0] == 0:
        conn.execute("INSERT INTO schema_version(version) VALUES (?)", (SCHEMA_VERSION,))
    else:
        conn.execute("UPDATE schema_version SET version = ? WHERE version < ?",
                     (SCHEMA_VERSION, SCHEMA_VERSION))


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


class ThreadLocalConnections:
    """One lazily opened connection per thread (for concurrent panel reads)."""

    def __init__(self, path: str) -> None:
        self._path = path
        self._local = threading.local()

    def get(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = self._local.conn = connect(self._path)
        return conn


def insert_records(
    conn: sqlite3.Connection, device_id: str, records: list[Record], received_at_ms: int
) -> tuple[int, int]:
    """Insert in one transaction; returns (accepted, duplicates)."""
    accepted = 0
    conn.execute("BEGIN IMMEDIATE")
    try:
        for r in records:
            cur = conn.execute(
                "INSERT OR IGNORE INTO records"
                "(id, device_id, session_id, seq, ts, type, data, received_at)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (str(r.id), device_id, str(r.session_id), r.seq, r.ts, r.type,
                 json.dumps(r.payload()), received_at_ms),
            )
            accepted += cur.rowcount
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    return accepted, len(records) - accepted
