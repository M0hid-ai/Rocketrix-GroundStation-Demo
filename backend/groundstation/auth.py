"""Login for the dashboard: PBKDF2 password hashes + HMAC-signed session cookies.

Users come from the ``GS_USERS`` environment variable (hosted deployments) or, if that is
unset, from ``backend/users.txt`` (local, git-ignored). One user per line (or ``;``-separated
in the env var)::

    alice:pbkdf2_sha256$600000$<salt hex>$<hash hex>

Create a line with ``python -m groundstation.auth <username>`` (prompts for the password).
Plain-text passwords are never stored. Sessions are signed with ``GS_SECRET``; without it a
random secret is kept in the data directory so logins survive restarts.
"""

from __future__ import annotations

import base64
import getpass
import hashlib
import hmac
import os
import secrets
import sys
import time
from collections import defaultdict, deque
from pathlib import Path

COOKIE = "gs_session"
SESSION_TTL_S = 7 * 24 * 3600
PBKDF2_ITERATIONS = 600_000
LOGIN_WINDOW_S = 300
LOGIN_MAX_FAILURES = 10  # per client IP per window

_DUMMY_HASH = None  # compared against for unknown users so timing does not leak usernames


def hash_password(password: str, iterations: int = PBKDF2_ITERATIONS) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algo, iters, salt, digest = encoded.split("$")
        if algo != "pbkdf2_sha256":
            return False
        test = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iters))
        return hmac.compare_digest(test.hex(), digest)
    except ValueError:
        return False


def parse_users(text: str) -> dict[str, str]:
    users: dict[str, str] = {}
    for raw in text.replace(";", "\n").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        name, sep, encoded = line.partition(":")
        if sep and name.strip() and encoded.strip():
            users[name.strip()] = encoded.strip()
    return users


class Auth:
    def __init__(self, users: dict[str, str], secret: bytes) -> None:
        self.users = users
        self.secret = secret
        self._failures: dict[str, deque[float]] = defaultdict(deque)

    @classmethod
    def from_environment(cls, users_file: Path, data_dir: Path) -> "Auth":
        env_users = os.environ.get("GS_USERS")
        if env_users is not None:
            users = parse_users(env_users)
        elif users_file.exists():
            users = parse_users(users_file.read_text(encoding="utf-8"))
        else:
            users = {}
        return cls(users, _load_secret(data_dir))

    # ---- passwords -------------------------------------------------------------------------

    def check_password(self, username: str, password: str) -> bool:
        global _DUMMY_HASH
        encoded = self.users.get(username)
        if encoded is None:
            if _DUMMY_HASH is None:
                _DUMMY_HASH = hash_password(secrets.token_hex(8))
            verify_password(password, _DUMMY_HASH)
            return False
        return verify_password(password, encoded)

    def rate_limited(self, client: str) -> bool:
        q = self._failures[client]
        cutoff = time.monotonic() - LOGIN_WINDOW_S
        while q and q[0] < cutoff:
            q.popleft()
        return len(q) >= LOGIN_MAX_FAILURES

    def record_failure(self, client: str) -> None:
        self._failures[client].append(time.monotonic())

    # ---- sessions --------------------------------------------------------------------------

    def issue(self, username: str) -> str:
        expires = int(time.time()) + SESSION_TTL_S
        body = base64.urlsafe_b64encode(f"{username}|{expires}".encode()).decode()
        return f"{body}.{self._sign(body)}"

    def verify(self, token: str | None) -> str | None:
        """Return the username for a valid, unexpired session token, else None."""
        if not token or "." not in token:
            return None
        body, sig = token.rsplit(".", 1)
        if not hmac.compare_digest(sig, self._sign(body)):
            return None
        try:
            username, expires = base64.urlsafe_b64decode(body.encode()).decode().rsplit("|", 1)
            if int(expires) < time.time():
                return None
        except (ValueError, UnicodeDecodeError):
            return None
        return username if username in self.users else None  # removed users lose access

    def _sign(self, body: str) -> str:
        return hmac.new(self.secret, body.encode(), hashlib.sha256).hexdigest()


def _load_secret(data_dir: Path) -> bytes:
    env = os.environ.get("GS_SECRET")
    if env:
        return env.encode()
    path = data_dir / ".session-secret"
    try:
        if path.exists():
            return path.read_bytes()
        data_dir.mkdir(parents=True, exist_ok=True)
        secret = secrets.token_bytes(32)
        path.write_bytes(secret)
        return secret
    except OSError:  # read-only filesystem: sessions last until the next restart
        return secrets.token_bytes(32)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python -m groundstation.auth <username>")
    pw = getpass.getpass(f"Password for {sys.argv[1]}: ")
    if len(pw) < 8:
        sys.exit("password must be at least 8 characters")
    if pw != getpass.getpass("Repeat: "):
        sys.exit("passwords do not match")
    print(f"{sys.argv[1]}:{hash_password(pw)}")
