"""Chat import: files -> parser adapter -> normalized messages -> SQLite.

Streaming and batched so archives with hundreds of thousands of messages do
not need to fit in memory. Re-importing the same export is idempotent.
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

from memory_museum.db import dumps
from memory_museum.parsers import ChatParser, ImportReport, ParsedMessage, detect_parser, get_parser
from memory_museum.timeutil import fmt

BATCH_SIZE = 5000

_INSERT = """
INSERT OR IGNORE INTO messages (
    conversation_id, sender_id, sender_name, ts, day, hour, msg_type, text,
    reply_to_source_id, media_ref, source_file, source_message_id, metadata, dedupe_key, import_run
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

SKIP_NAMES = {".ds_store", "thumbs.db", "desktop.ini"}


def iter_input_files(inputs: Iterable[Path | str]) -> list[Path]:
    files: list[Path] = []
    for raw in inputs:
        p = Path(raw)
        if p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file() and not any(part.startswith(".") for part in f.relative_to(p).parts) \
                        and f.name.lower() not in SKIP_NAMES:
                    files.append(f)
        elif p.is_file():
            files.append(p)
    return files


def _content_base(m: ParsedMessage) -> str:
    return "|".join([
        m.conversation_id or "main",
        fmt(m.timestamp) or "",
        m.sender_id or "",
        m.message_type,
        m.text or "",
        m.media_reference or "",
    ])


def dedupe_key(m: ParsedMessage, occurrence: int = 0) -> str:
    """Stable identity for a message.

    Uses the export's own message id when present. Otherwise a content hash plus
    the occurrence index within the file, so two genuine identical messages in
    the same minute ("好", "好") are both kept, while re-importing the same or an
    overlapping export does not create duplicates.
    """
    if m.source_message_id:
        base = f"id|{m.conversation_id or 'main'}|{m.source_message_id}"
    else:
        base = f"c|{_content_base(m)}|{occurrence}"
    return hashlib.sha1(base.encode("utf-8")).hexdigest()


def start_run(conn: sqlite3.Connection, kind: str, source: str) -> int:
    cur = conn.execute("INSERT INTO import_runs(kind, source, started_at) VALUES (?, ?, ?)",
                       (kind, source, datetime.now().isoformat(timespec="seconds")))
    conn.commit()
    return int(cur.lastrowid)


def finish_run(conn: sqlite3.Connection, run_id: int, report: dict) -> None:
    conn.execute("UPDATE import_runs SET finished_at = ?, report = ? WHERE id = ?",
                 (datetime.now().isoformat(timespec="seconds"), dumps(report), run_id))
    conn.commit()


def import_chat(
    conn: sqlite3.Connection,
    inputs: Iterable[Path | str],
    *,
    parser: str | None = None,
    conversation: str | None = None,
    tz=None,
    progress: Callable[[str], None] | None = None,
) -> ImportReport:
    report = ImportReport()
    files = iter_input_files(inputs)
    run_id = start_run(conn, "chat", ";".join(str(i) for i in inputs))
    forced: ChatParser | None = get_parser(parser) if parser else None

    for path in files:
        chosen = forced or detect_parser(path)
        if chosen is None:
            report.issue("unsupported_file", path, None, "no parser recognises this file; skipped")
            continue
        report.files.append(str(path))
        if progress:
            progress(f"{chosen.name}: {path}")
        occurrences: dict[bytes, int] = {}
        batch: list[tuple] = []
        try:
            for m in chosen.parse(path, report, tz=tz):
                if conversation:
                    m.conversation_id = conversation
                base = hashlib.sha1(_content_base(m).encode("utf-8")).digest()
                occ = occurrences.get(base, 0)
                occurrences[base] = occ + 1
                ts = fmt(m.timestamp)
                batch.append((
                    m.conversation_id or "main",
                    m.sender_id,
                    m.sender_display_name,
                    ts,
                    ts[:10] if ts else None,
                    m.timestamp.hour if m.timestamp else None,
                    m.message_type,
                    m.text,
                    m.reply_to_message_id,
                    m.media_reference,
                    m.source_file,
                    m.source_message_id,
                    dumps(m.metadata) if m.metadata else None,
                    dedupe_key(m, occ),
                    run_id,
                ))
                report.by_type[m.message_type] += 1
                if m.sender_id:
                    report.participants[m.sender_display_name or m.sender_id] += 1
                if ts:
                    if report.first_ts is None or ts < report.first_ts:
                        report.first_ts = ts
                    if report.last_ts is None or ts > report.last_ts:
                        report.last_ts = ts
                if len(batch) >= BATCH_SIZE:
                    _flush(conn, batch, report)
        except Exception as e:  # a broken file must not break the whole import
            report.issue("unreadable_file", path, None, f"parser stopped early: {type(e).__name__}: {e}")
        _flush(conn, batch, report)

    _post_process(conn)
    finish_run(conn, run_id, report.to_dict())
    return report


def _flush(conn: sqlite3.Connection, batch: list[tuple], report: ImportReport) -> None:
    if not batch:
        return
    before = conn.total_changes
    conn.executemany(_INSERT, batch)
    inserted = conn.total_changes - before
    report.imported += inserted
    report.duplicates += len(batch) - inserted
    conn.commit()
    batch.clear()


def merge_name_only_senders(conn: sqlite3.Connection) -> int:
    """Text exports often identify people by display name only ("林夏") while
    other exports use ids ("xia" named "林夏"). Fold the name-only identity into
    the id-based one, but only when that name belongs to exactly one id."""
    owners: dict[str, set[str]] = {}
    for r in conn.execute("SELECT DISTINCT sender_id, sender_name FROM messages "
                          "WHERE sender_id IS NOT NULL AND sender_name IS NOT NULL AND sender_id != sender_name"):
        owners.setdefault(r["sender_name"], set()).add(r["sender_id"])
    merged = 0
    for name, ids in owners.items():
        if len(ids) != 1:
            continue
        cur = conn.execute("UPDATE messages SET sender_id = ? WHERE sender_id = ? AND sender_name = ?",
                           (next(iter(ids)), name, name))
        merged += cur.rowcount
    if merged:
        conn.execute("DELETE FROM participants WHERE id NOT IN (SELECT DISTINCT sender_id FROM messages "
                     "WHERE sender_id IS NOT NULL)")
    return merged


def _post_process(conn: sqlite3.Connection) -> None:
    merge_name_only_senders(conn)
    conn.execute(
        """
        UPDATE messages SET reply_to_message_id = (
            SELECT m2.id FROM messages m2
            WHERE m2.conversation_id = messages.conversation_id AND m2.source_message_id = messages.reply_to_source_id
            LIMIT 1)
        WHERE reply_to_source_id IS NOT NULL AND reply_to_message_id IS NULL
        """
    )
    conn.execute(
        """
        INSERT INTO participants(id, display_name, message_count)
        SELECT sender_id,
               (SELECT sender_name FROM messages m2 WHERE m2.sender_id = m.sender_id AND sender_name IS NOT NULL
                GROUP BY sender_name ORDER BY COUNT(*) DESC LIMIT 1),
               COUNT(*)
        FROM messages m WHERE sender_id IS NOT NULL GROUP BY sender_id
        ON CONFLICT(id) DO UPDATE SET message_count = excluded.message_count,
            display_name = COALESCE(participants.display_name, excluded.display_name)
        """
    )
    conn.execute("INSERT OR IGNORE INTO conversations(id) SELECT DISTINCT conversation_id FROM messages")
    conn.commit()
