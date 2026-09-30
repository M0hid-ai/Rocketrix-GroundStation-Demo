import os
import tempfile

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from groundstation.auth import Auth, hash_password, parse_users, verify_password

# Configure the server before importing it: one known user, throwaway data directory.
os.environ["GS_USERS"] = f"tester:{hash_password('correct horse', iterations=1000)}"
os.environ["GS_DATA_DIR"] = tempfile.mkdtemp()
os.environ["GS_SECRET"] = "test-secret"

from groundstation import main  # noqa: E402


@pytest.fixture()
def client():
    main.auth._failures.clear()
    with TestClient(main.app) as c:
        yield c


def login(c, password="correct horse"):
    return c.post("/api/auth/login", json={"username": "tester", "password": password})


def test_password_hash_roundtrip():
    encoded = hash_password("s3cret-pass", iterations=1000)
    assert "s3cret-pass" not in encoded
    assert verify_password("s3cret-pass", encoded)
    assert not verify_password("wrong", encoded)
    assert not verify_password("s3cret-pass", "garbage")


def test_parse_users_accepts_lines_and_semicolons():
    users = parse_users("# comment\na:hash1\n\nb:hash2;c:hash3")
    assert users == {"a": "hash1", "b": "hash2", "c": "hash3"}


def test_session_tokens_are_tamper_proof():
    auth = Auth({"a": "x"}, b"k")
    token = auth.issue("a")
    assert auth.verify(token) == "a"
    assert auth.verify(token[:-1] + ("0" if token[-1] != "0" else "1")) is None
    assert Auth({"a": "x"}, b"other-key").verify(token) is None
    assert Auth({}, b"k").verify(token) is None  # user removed -> session invalid


def test_api_requires_login(client):
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/config").status_code == 401
    assert client.post("/api/command/arm").status_code == 401
    assert client.get("/docs").status_code == 401
    assert login(client, "nope").status_code == 401
    assert login(client).status_code == 200
    assert client.get("/api/auth/me").json() == {"user": "tester"}
    assert client.get("/api/config").status_code == 200
    client.post("/api/auth/logout")
    assert client.get("/api/config").status_code == 401


def test_login_is_rate_limited(client):
    for _ in range(10):
        assert login(client, "bad").status_code == 401
    assert login(client).status_code == 429


def test_websocket_requires_session_and_same_origin(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws"):
            pass
    login(client)
    with client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["type"] == "hello"
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws", headers={"origin": "https://evil.example"}):
            pass
