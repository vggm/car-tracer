import pytest

from app import confirmations
from app.db import connect

NOW = 1763481600000


@pytest.fixture
def conn(tmp_path):
    return connect(str(tmp_path / "c.db"))


def test_valid_once(conn):
    cid = confirmations.create_confirmation(conn, NOW)
    assert len(cid) == 36
    assert confirmations.consume_confirmation(conn, cid, NOW + 1000) is True
    assert confirmations.consume_confirmation(conn, cid, NOW + 2000) is False


def test_expired(conn):
    cid = confirmations.create_confirmation(conn, NOW)
    assert confirmations.consume_confirmation(
        conn, cid, NOW + confirmations.CLEAR_CONFIRM_MS + 1) is False


def test_boundary_is_valid(conn):
    cid = confirmations.create_confirmation(conn, NOW)
    assert confirmations.consume_confirmation(
        conn, cid, NOW + confirmations.CLEAR_CONFIRM_MS) is True


def test_expired_is_marked_used(conn):
    cid = confirmations.create_confirmation(conn, NOW)
    confirmations.consume_confirmation(conn, cid, NOW + 400_000)
    assert confirmations.consume_confirmation(conn, cid, NOW + 1) is False


def test_unknown(conn):
    assert confirmations.consume_confirmation(conn, "nope", NOW) is False
