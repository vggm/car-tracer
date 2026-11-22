from app.db import connect


def test_connect_is_idempotent(tmp_path):
    p = str(tmp_path / "x.db")
    c1 = connect(p)
    c1.close()
    c2 = connect(p)
    assert c2.execute("SELECT version FROM schema_version").fetchall() == [(3,)]
    assert c2.execute("SELECT count(*) FROM records").fetchone() == (0,)


def test_wal_enabled(tmp_path):
    c = connect(str(tmp_path / "x.db"))
    assert c.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert c.execute("PRAGMA busy_timeout").fetchone()[0] == 5000


def test_migration_adds_kind_to_old_database(tmp_path):
    import sqlite3
    p = str(tmp_path / "old.db")
    raw = sqlite3.connect(p)
    raw.executescript(
        "CREATE TABLE scan_requests (id TEXT PRIMARY KEY, requested_at INTEGER NOT NULL,"
        " done_at INTEGER, result TEXT);"
        "CREATE TABLE schema_version (version INTEGER NOT NULL);"
        "INSERT INTO schema_version VALUES (1);"
        "INSERT INTO scan_requests(id, requested_at) VALUES ('old', 5);"
    )
    raw.commit()
    raw.close()
    c = connect(p)
    assert c.execute("SELECT id, requested_at, kind FROM scan_requests").fetchall() == [
        ("old", 5, "read_dtc")
    ]
    assert c.execute("SELECT version FROM schema_version").fetchall() == [(3,)]
    c.close()
    c = connect(p)
    assert c.execute("SELECT count(*) FROM scan_requests").fetchone() == (1,)
    assert c.execute("SELECT version FROM schema_version").fetchall() == [(3,)]
    assert c.execute("SELECT count(*) FROM clear_confirmations").fetchone() == (0,)


def test_range_trips_query_uses_ts_index(tmp_path):
    c = connect(str(tmp_path / "x.db"))
    plan = " ".join(
        r[3] for r in c.execute(
            "EXPLAIN QUERY PLAN SELECT ts, type, data FROM records"
            " WHERE ts BETWEEN ? AND ? ORDER BY ts, seq", (0, 10)))
    assert "records_ts" in plan and "SCAN records" not in plan


def test_connect_writer_does_not_run_schema(tmp_path):
    import sqlite3

    from app.db import connect_writer

    p = str(tmp_path / "fresh.db")
    c = connect_writer(p)
    tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    assert "journeys" not in tables
    assert c.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert c.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    assert isinstance(c, sqlite3.Connection)
