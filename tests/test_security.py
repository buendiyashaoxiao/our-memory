import pytest
from fastapi.testclient import TestClient

from memory_museum import security
from memory_museum.api.app import create_app
from memory_museum.db import open_db


def test_pin_hash_roundtrip():
    stored = security.hash_pin("2468", iterations=1000)
    assert security.verify_pin("2468", stored)
    assert not security.verify_pin("1357", stored)
    assert "2468" not in str(stored)
    assert not security.verify_pin("x", {"broken": True})


def test_pin_validation():
    with pytest.raises(ValueError):
        security.validate_new_pin("123")


def test_session_idle_expiry():
    store = security.SessionStore()
    tok = store.create()
    assert store.touch(tok, idle_timeout=0)
    store.sessions[tok] -= 1000
    assert not store.touch(tok, idle_timeout=60)
    assert not store.touch("nope", 0)


@pytest.fixture
def client(paths):
    with TestClient(create_app(paths, frontend_dist=None)) as c:
        yield c


def test_lock_gates_the_api_and_media(client, paths):
    assert client.get("/api/overview").status_code == 200
    r = client.post("/api/lock/pin", json={"current": None, "new": "2468"})
    assert r.json() == {"enabled": True}
    client.cookies.clear()
    assert client.get("/api/overview").status_code == 401
    assert client.get("/api/media/1/file").status_code == 401
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/lock/status").json()["unlocked"] is False
    assert client.post("/api/lock/unlock", json={"pin": "0000"}).status_code == 403
    assert client.post("/api/lock/unlock", json={"pin": "2468"}).status_code == 200
    assert client.get("/api/overview").status_code == 200
    client.post("/api/lock/lock")
    assert client.get("/api/overview").status_code == 401
    # a wrong current PIN cannot change the PIN
    client.post("/api/lock/unlock", json={"pin": "2468"})
    assert client.post("/api/lock/pin", json={"current": "0000", "new": "9999"}).status_code == 403
    assert client.post("/api/lock/pin", json={"current": "2468", "new": None}).json() == {"enabled": False}
    client.cookies.clear()
    assert client.get("/api/overview").status_code == 200
    conn = open_db(paths.db)
    assert not security.lock_enabled(conn)
    conn.close()


def test_brute_force_is_throttled(client):
    client.post("/api/lock/pin", json={"new": "2468"})
    client.cookies.clear()
    codes = [client.post("/api/lock/unlock", json={"pin": "0000"}).status_code for _ in range(6)]
    assert codes[:5] == [403] * 5 and codes[5] == 429
