from app.db import connect


def test_connect_is_idempotent(tmp_path):
    p = str(tmp_path / "x.db")
    c1 = connect(p)
    c1.close()
    c2 = connect(p)
    assert c2.execute("SELECT version FROM schema_version").fetchall() == [(1,)]
    assert c2.execute("SELECT count(*) FROM records").fetchone() == (0,)


def test_wal_enabled(tmp_path):
    c = connect(str(tmp_path / "x.db"))
    assert c.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert c.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
