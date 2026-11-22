import threading

from app.db import ThreadLocalConnections, connect


def test_thread_local_connections(tmp_path):
    path = str(tmp_path / "r.db")
    writer = connect(path)
    writer.execute("INSERT INTO schema_version(version) VALUES (99)")
    readers = ThreadLocalConnections(path)

    a, b = readers.get(), readers.get()
    assert a is b
    seen = {}

    def work():
        c1, c2 = readers.get(), readers.get()
        seen["same"] = c1 is c2
        seen["conn"] = c1
        seen["rows"] = c1.execute("SELECT version FROM schema_version").fetchall()

    t = threading.Thread(target=work)
    t.start()
    t.join()
    assert seen["same"] and seen["conn"] is not a
    assert (99,) in seen["rows"]
    assert (99,) in a.execute("SELECT version FROM schema_version").fetchall()
