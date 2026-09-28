"""SQLite storage. One file, no server, no external database.

The schema separates *imported facts* (messages, media, derived metadata) from
*user curation* (favorites, titles, notes, moments, hidden flags, settings) so
re-imports never wipe what the user wrote.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    name TEXT,
    source TEXT
);

CREATE TABLE IF NOT EXISTS participants (
    id TEXT PRIMARY KEY,
    display_name TEXT,
    message_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY,
    conversation_id TEXT NOT NULL DEFAULT 'main',
    sender_id TEXT,
    sender_name TEXT,
    ts TEXT,
    day TEXT,
    hour INTEGER,
    msg_type TEXT NOT NULL DEFAULT 'text',
    text TEXT,
    reply_to_source_id TEXT,
    reply_to_message_id INTEGER,
    media_ref TEXT,
    source_file TEXT,
    source_message_id TEXT,
    metadata TEXT,
    dedupe_key TEXT NOT NULL UNIQUE,
    hidden INTEGER NOT NULL DEFAULT 0,
    import_run INTEGER
);
CREATE INDEX IF NOT EXISTS idx_messages_day ON messages(day, ts, id);
CREATE INDEX IF NOT EXISTS idx_messages_ts ON messages(ts, id);
CREATE INDEX IF NOT EXISTS idx_messages_type_day ON messages(msg_type, day);
CREATE INDEX IF NOT EXISTS idx_messages_media_ref ON messages(media_ref) WHERE media_ref IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_messages_source ON messages(conversation_id, source_message_id);

CREATE TABLE IF NOT EXISTS media (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,
    rel_path TEXT,
    media_type TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    ext TEXT,
    size_bytes INTEGER,
    mtime REAL,
    hash TEXT,
    duplicate_of INTEGER,
    ts TEXT,
    day TEXT,
    ts_source TEXT,
    original_ts TEXT,
    original_ts_source TEXT,
    duration REAL,
    width INTEGER,
    height INTEGER,
    orientation INTEGER,
    codec TEXT,
    metadata TEXT,
    status TEXT NOT NULL DEFAULT 'ok',
    error TEXT,
    thumb_path TEXT,
    playable_path TEXT,
    waveform TEXT,
    message_id INTEGER,
    association_method TEXT,
    association_confidence TEXT,
    suggested_message_id INTEGER,
    association_locked INTEGER NOT NULL DEFAULT 0,
    user_title TEXT,
    user_note TEXT,
    hidden INTEGER NOT NULL DEFAULT 0,
    import_run INTEGER
);
CREATE INDEX IF NOT EXISTS idx_media_day ON media(day, ts, id);
CREATE INDEX IF NOT EXISTS idx_media_type_ts ON media(media_type, ts, id);
CREATE INDEX IF NOT EXISTS idx_media_hash ON media(hash);
CREATE INDEX IF NOT EXISTS idx_media_name ON media(original_filename COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_media_message ON media(message_id);

CREATE TABLE IF NOT EXISTS favorites (
    kind TEXT NOT NULL,
    ref TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (kind, ref)
);

CREATE TABLE IF NOT EXISTS moments (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    start_day TEXT,
    end_day TEXT,
    cover_media_id INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS moment_items (
    moment_id INTEGER NOT NULL REFERENCES moments(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    ref INTEGER NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (moment_id, kind, ref)
);

CREATE TABLE IF NOT EXISTS hidden_days (
    day TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS import_runs (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    source TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    report TEXT
);

CREATE TABLE IF NOT EXISTS day_summary (
    day TEXT PRIMARY KEY,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    msg_count INTEGER NOT NULL DEFAULT 0,
    text_count INTEGER NOT NULL DEFAULT 0,
    text_chars INTEGER NOT NULL DEFAULT 0,
    photo_count INTEGER NOT NULL DEFAULT 0,
    video_count INTEGER NOT NULL DEFAULT 0,
    voice_count INTEGER NOT NULL DEFAULT 0,
    audio_seconds REAL NOT NULL DEFAULT 0,
    first_ts TEXT,
    last_ts TEXT,
    longest_session_minutes INTEGER NOT NULL DEFAULT 0,
    score REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_day_summary_ym ON day_summary(year, month, day);

CREATE TABLE IF NOT EXISTS stats_cache (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def connect(path: Path | str, *, check_same_thread: bool = True) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), check_same_thread=check_same_thread, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()


def open_db(path: Path | str, *, check_same_thread: bool = True) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = connect(path, check_same_thread=check_same_thread)
    init_db(conn)
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def loads(value: str | None, default: Any = None) -> Any:
    if value is None:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None
