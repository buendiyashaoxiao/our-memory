"""User settings stored in the local database (never in the repository)."""

from __future__ import annotations

import copy
import json
import sqlite3
from typing import Any

from memory_museum.config import COPY_FILE
from memory_museum.db import dumps, loads

DEFAULT_SETTINGS: dict[str, Any] = {
    # sender_id -> {"name": str, "avatar": str | None}
    "participants": {},
    # which sender_id is "me" (messages aligned right); None = first participant
    "self_id": None,
    "relationship_start": None,
    "title": None,
    "intro_lines": None,
    "language": "zh",
    "date_format": "long",  # long | numeric
    "theme": "auto",  # auto | light | dark
    "timezone": "local",
    "random_day": {
        "mode": "weighted",  # weighted | uniform
        "photo": 1.0,
        "voice": 1.0,
        "video": 1.0,
        "conversation": 1.0,
        "min_messages": 5,
    },
    "autoplay": False,
    "auto_lock_minutes": 0,
}

PUBLIC_KEYS = set(DEFAULT_SETTINGS)


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def get_settings(conn: sqlite3.Connection) -> dict[str, Any]:
    stored = {row["key"]: loads(row["value"]) for row in conn.execute("SELECT key, value FROM settings")}
    user = {k: v for k, v in stored.items() if k in PUBLIC_KEYS}
    return _merge(DEFAULT_SETTINGS, user)


def update_settings(conn: sqlite3.Connection, patch: dict[str, Any]) -> dict[str, Any]:
    current = get_settings(conn)
    for key, value in patch.items():
        if key not in PUBLIC_KEYS:
            raise KeyError(f"unknown setting: {key}")
        if isinstance(value, dict) and isinstance(current.get(key), dict) and key != "participants":
            value = _merge(current[key], value)
        conn.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, dumps(value)),
        )
    conn.commit()
    return get_settings(conn)


def get_private(conn: sqlite3.Connection, key: str, default: Any = None) -> Any:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (f"_{key}",)).fetchone()
    return loads(row["value"], default) if row else default


def set_private(conn: sqlite3.Connection, key: str, value: Any) -> None:
    if value is None:
        conn.execute("DELETE FROM settings WHERE key = ?", (f"_{key}",))
    else:
        conn.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (f"_{key}", dumps(value)),
        )
    conn.commit()


def load_copy(language: str = "zh") -> dict[str, Any]:
    try:
        data = json.loads(COPY_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return dict(data.get(language) or data.get("zh") or {})


def effective_copy(conn: sqlite3.Connection) -> dict[str, Any]:
    s = get_settings(conn)
    copy_ = load_copy(s["language"])
    if s.get("title"):
        copy_["museumTitle"] = s["title"]
    if s.get("intro_lines"):
        copy_["introLines"] = s["intro_lines"]
    return copy_


def display_names(conn: sqlite3.Connection) -> dict[str, str]:
    """sender_id -> name, preferring user-configured names over imported ones."""
    names = {r["id"]: r["display_name"] or r["id"] for r in conn.execute("SELECT id, display_name FROM participants")}
    for sid, info in (get_settings(conn).get("participants") or {}).items():
        if isinstance(info, dict) and info.get("name"):
            names[sid] = info["name"]
    return names
