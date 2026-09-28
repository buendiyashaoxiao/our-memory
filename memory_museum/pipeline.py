"""Staged imports with a preview step.

Imports run against a *copy* of the database (``museum.staging.db``). The user
sees a preview, then either commits (the staging copy replaces the live data
via SQLite's online backup API, safe even while the server is running) or
discards it. Existing favorites, notes, moments and settings are carried over
because the staging copy starts from the current database.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from memory_museum.association import AssociationReport, associate
from memory_museum.config import Paths
from memory_museum.db import connect, open_db
from memory_museum.importer import import_chat
from memory_museum.index import build_index
from memory_museum.media.scanner import MediaReport, import_media
from memory_museum.parsers import ImportReport
from memory_museum.settings import get_settings
from memory_museum.timeutil import get_tz


@dataclass
class PipelineResult:
    chat: ImportReport | None = None
    media: MediaReport | None = None
    association: AssociationReport | None = None
    index: dict[str, Any] = field(default_factory=dict)
    totals: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "chat": self.chat.to_dict() if self.chat else None,
            "media": self.media.to_dict() if self.media else None,
            "association": self.association.to_dict() if self.association else None,
            "index": self.index,
            "totals": self.totals,
        }


def _remove_db_files(path: Path) -> None:
    for suffix in ("", "-wal", "-shm", "-journal"):
        p = Path(str(path) + suffix)
        if p.exists():
            p.unlink()


def open_staging(paths: Paths) -> sqlite3.Connection:
    paths.ensure()
    _remove_db_files(paths.staging_db)
    staging = open_db(paths.staging_db)
    if paths.db.exists():
        live = connect(paths.db)
        try:
            live.backup(staging)
        finally:
            live.close()
        staging.close()
        staging = open_db(paths.staging_db)  # re-run schema to apply any additions
    return staging


def commit_staging(paths: Paths) -> None:
    staging = connect(paths.staging_db)
    live = open_db(paths.db)
    try:
        staging.backup(live)
    finally:
        live.close()
        staging.close()
    _remove_db_files(paths.staging_db)


def discard_staging(paths: Paths) -> None:
    _remove_db_files(paths.staging_db)


def totals(conn: sqlite3.Connection) -> dict[str, Any]:
    msg = conn.execute("SELECT COUNT(*), MIN(day), MAX(day), SUM(ts IS NULL) FROM messages").fetchone()
    by_type = {r[0]: r[1] for r in conn.execute("SELECT media_type, COUNT(*) FROM media GROUP BY media_type")}
    by_status = {r[0]: r[1] for r in conn.execute("SELECT status, COUNT(*) FROM media GROUP BY status")}
    conf = {r[0] or "none": r[1] for r in conn.execute(
        "SELECT association_confidence, COUNT(*) FROM media WHERE message_id IS NOT NULL GROUP BY association_confidence")}
    return {
        "messages": msg[0],
        "first_day": msg[1],
        "last_day": msg[2],
        "undated_messages": msg[3] or 0,
        "participants": [dict(r) for r in conn.execute(
            "SELECT id, display_name, message_count FROM participants ORDER BY message_count DESC")],
        "media_by_type": by_type,
        "media_by_status": by_status,
        "duplicates": conn.execute("SELECT COUNT(*) FROM media WHERE duplicate_of IS NOT NULL").fetchone()[0],
        "linked_by_confidence": conf,
        "low_suggestions": conn.execute(
            "SELECT COUNT(*) FROM media WHERE message_id IS NULL AND suggested_message_id IS NOT NULL").fetchone()[0],
        "unlinked_media": conn.execute(
            "SELECT COUNT(*) FROM media WHERE message_id IS NULL AND duplicate_of IS NULL").fetchone()[0],
    }


def run_import(
    conn: sqlite3.Connection,
    paths: Paths,
    *,
    chat_inputs: Iterable[Path | str] = (),
    media_inputs: Iterable[Path | str] = (),
    parser: str | None = None,
    conversation: str | None = None,
    timezone: str | None = None,
    log: Callable[[str], None] | None = None,
) -> PipelineResult:
    log = log or (lambda _msg: None)
    result = PipelineResult()
    tz = get_tz(timezone or get_settings(conn).get("timezone"))
    if timezone and tz is None and timezone != "local":
        raise ValueError(f"unknown timezone {timezone!r} (try e.g. Asia/Shanghai or UTC+8)")
    chat_inputs, media_inputs = list(chat_inputs), list(media_inputs)
    if chat_inputs:
        log("Reading chat files ...")
        result.chat = import_chat(conn, chat_inputs, parser=parser, conversation=conversation, tz=tz,
                                  progress=lambda s: log(f"  {s}"))
    if media_inputs:
        log("Scanning media (metadata, thumbnails) ...")
        result.media = import_media(conn, media_inputs, paths,
                                    progress=lambda d, t: log(f"  {d}/{t} files"))
    log("Linking media to messages ...")
    result.association = associate(conn)
    log("Building day index and statistics ...")
    result.index = build_index(conn)
    result.totals = totals(conn)
    return result


def _n(v: Any) -> str:
    return f"{v:,}" if isinstance(v, int) else str(v)


def format_preview(result: PipelineResult) -> str:
    t = result.totals
    mt = t.get("media_by_type", {})
    lines = ["", "Detected (in the museum after this import):", ""]
    lines.append(f"  {_n(t['messages'])} messages")
    lines.append(f"  {_n(mt.get('image', 0))} images")
    lines.append(f"  {_n(mt.get('voice', 0))} voice messages, {_n(mt.get('audio', 0))} other audio")
    lines.append(f"  {_n(mt.get('video', 0))} videos")
    lines += ["", "Date range:", f"  {t.get('first_day') or '-'} -> {t.get('last_day') or '-'}"]
    lines += ["", "Participants:"]
    for p in t.get("participants", []):
        lines.append(f"  {p['display_name'] or p['id']}  ({_n(p['message_count'])} messages)")
    conf = t.get("linked_by_confidence", {})
    lines += ["", "Media associations:",
              f"  Exact: {_n(conf.get('exact', 0))}",
              f"  High confidence: {_n(conf.get('high', 0))}",
              f"  Medium confidence: {_n(conf.get('medium', 0))}",
              f"  Low (suggestion only, not linked): {_n(t.get('low_suggestions', 0))}",
              f"  Unlinked media files: {_n(t.get('unlinked_media', 0))}"]
    if result.association:
        a = result.association
        lines.append(f"  Chat media references with no matching file: {_n(a.unresolved_refs)}")
        lines.append(f"  Media messages without any file: {_n(a.media_messages_without_file)}")

    warnings: list[str] = []
    if result.chat:
        c = result.chat
        lines += ["", "This chat import:",
                  f"  records read: {_n(c.records_seen)}, new: {_n(c.imported)}, duplicates skipped: {_n(c.duplicates)}"]
        for kind, n in sorted(c.issue_counts.items()):
            warnings.append(f"{kind.replace('_', ' ')}: {_n(n)}")
        for issue in c.issues[:8]:
            warnings.append(f"  e.g. {Path(issue['file']).name if issue['file'] else ''} {issue['where'] or ''}: "
                            f"{issue['detail']}")
    if t.get("undated_messages"):
        warnings.append(f"messages without a usable date (kept, not on the timeline): {_n(t['undated_messages'])}")
    if result.media:
        m = result.media
        lines += ["", "This media scan:",
                  f"  files: {_n(m.files_seen)} (new {_n(m.new)}, updated {_n(m.updated)}, unchanged {_n(m.unchanged)})",
                  f"  capture time from: " + ", ".join(f"{k} {v}" for k, v in sorted(m.ts_sources.items()))]
        if m.unsupported_files:
            warnings.append(f"files ignored (not photo/audio/video): {_n(m.unsupported_files)}")
        if m.duplicates:
            warnings.append(f"duplicate media files (shown once): {_n(m.duplicates)}")
        if m.missing_marked:
            warnings.append(f"media files no longer found on disk: {_n(m.missing_marked)}")
        for p in m.problems[:8]:
            warnings.append(f"  {p['status']}: {Path(p['file']).name}: {p['error']}")
        if not m.ffmpeg:
            warnings.append("ffmpeg not found: video thumbnails and audio/video durations are unavailable")
    if result.association and result.association.unresolved_examples:
        warnings.append("unmatched media references, e.g.: " + ", ".join(result.association.unresolved_examples[:5]))
    lines += ["", "Warnings:"] + ([f"  {w}" for w in warnings] or ["  none"])
    return "\n".join(lines) + "\n"
