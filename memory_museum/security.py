"""Optional local PIN lock.

IMPORTANT: this is an *access gate for the web UI*, not encryption. The
database and original media stay readable by anyone with access to the files
on disk. See docs/PRIVACY.md.

The PIN is stored as a salted PBKDF2-SHA256 hash. Unlocking yields a random
session token (HttpOnly cookie) kept only in server memory; restarting the
server locks everyone out again. Sessions expire after the configured idle
time.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass, field

from memory_museum.settings import get_private, get_settings, set_private

ITERATIONS = 240_000
MAX_FAILURES = 5
LOCKOUT_SECONDS = 30
COOKIE_NAME = "mm_session"


def hash_pin(pin: str, salt: bytes | None = None, iterations: int = ITERATIONS) -> dict:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, iterations)
    return {"salt": salt.hex(), "hash": digest.hex(), "iterations": iterations}


def verify_pin(pin: str, stored: dict) -> bool:
    try:
        digest = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), bytes.fromhex(stored["salt"]),
                                     int(stored["iterations"]))
    except (KeyError, ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), stored["hash"])


def validate_new_pin(pin: str) -> None:
    if not isinstance(pin, str) or not (4 <= len(pin) <= 64):
        raise ValueError("PIN/password must be 4-64 characters")


def lock_enabled(conn: sqlite3.Connection) -> bool:
    return bool(get_private(conn, "lock"))


def set_pin(conn: sqlite3.Connection, pin: str | None) -> None:
    if pin is None:
        set_private(conn, "lock", None)
        return
    validate_new_pin(pin)
    set_private(conn, "lock", hash_pin(pin))


def check_pin(conn: sqlite3.Connection, pin: str) -> bool:
    stored = get_private(conn, "lock")
    return bool(stored) and verify_pin(pin, stored)


def idle_timeout_seconds(conn: sqlite3.Connection) -> int:
    minutes = int(get_settings(conn).get("auto_lock_minutes") or 0)
    return minutes * 60 if minutes > 0 else 0


@dataclass
class SessionStore:
    sessions: dict[str, float] = field(default_factory=dict)
    failures: int = 0
    locked_until: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def create(self) -> str:
        token = secrets.token_urlsafe(32)
        with self._lock:
            self.sessions[token] = time.monotonic()
            self.failures = 0
        return token

    def touch(self, token: str | None, idle_timeout: int) -> bool:
        if not token:
            return False
        now = time.monotonic()
        with self._lock:
            last = self.sessions.get(token)
            if last is None:
                return False
            if idle_timeout and now - last > idle_timeout:
                del self.sessions[token]
                return False
            self.sessions[token] = now
            return True

    def revoke(self, token: str | None) -> None:
        with self._lock:
            self.sessions.pop(token or "", None)

    def revoke_all(self) -> None:
        with self._lock:
            self.sessions.clear()

    def throttled(self) -> float:
        remaining = self.locked_until - time.monotonic()
        return max(0.0, remaining)

    def record_failure(self) -> None:
        with self._lock:
            self.failures += 1
            if self.failures >= MAX_FAILURES:
                self.locked_until = time.monotonic() + LOCKOUT_SECONDS
                self.failures = 0
