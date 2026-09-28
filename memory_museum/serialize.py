"""Row -> API payload helpers with batched lookups (no N+1 queries)."""

from __future__ import annotations

import sqlite3
from typing import Any, Iterable, Sequence

from memory_museum.db import loads

MEDIA_COLUMNS = """id, media_type, original_filename, ts, day, ts_source, duration, width, height, status, error,
    thumb_path, playable_path, waveform, message_id, suggested_message_id, association_method,
    association_confidence, association_locked, user_title, user_note, hidden, duplicate_of, ext, size_bytes"""

BROWSER_AUDIO = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".opus", ".flac", ".webm", ".mp4"}
BROWSER_VIDEO = {".mp4", ".m4v", ".webm", ".mov"}


def favorites_set(conn: sqlite3.Connection, kind: str, refs: Iterable[Any]) -> set[str]:
    refs = [str(r) for r in refs]
    if not refs:
        return set()
    out: set[str] = set()
    for i in range(0, len(refs), 500):
        chunk = refs[i:i + 500]
        out |= {r[0] for r in conn.execute(
            f"SELECT ref FROM favorites WHERE kind = ? AND ref IN ({','.join('?' * len(chunk))})", [kind, *chunk])}
    return out


def media_payload(row: sqlite3.Row | dict, *, favorite: bool = False, sender_id: str | None = None) -> dict[str, Any]:
    r = dict(row)
    mid = r["id"]
    ext = (r.get("ext") or "").lower()
    playable = r["status"] == "ok" and (
        bool(r.get("playable_path"))
        or (r["media_type"] in ("voice", "audio") and ext in BROWSER_AUDIO)
        or (r["media_type"] == "video" and ext in BROWSER_VIDEO)
        or r["media_type"] == "image"
    )
    assoc = None
    if r.get("message_id") or r.get("suggested_message_id") or r.get("association_method"):
        assoc = {
            "message_id": r.get("message_id"),
            "suggested_message_id": r.get("suggested_message_id"),
            "method": r.get("association_method"),
            "confidence": r.get("association_confidence"),
            "locked": bool(r.get("association_locked")),
        }
    return {
        "id": mid,
        "type": r["media_type"],
        "filename": r["original_filename"],
        "ts": r["ts"],
        "day": r["day"],
        "ts_source": r["ts_source"],
        "duration": r["duration"],
        "width": r["width"],
        "height": r["height"],
        "status": r["status"],
        "error": r.get("error"),
        "thumb": f"/api/media/{mid}/thumb" if r.get("thumb_path") else None,
        "url": f"/api/media/{mid}/file",
        "playable": playable,
        "waveform": loads(r.get("waveform")),
        "title": r.get("user_title"),
        "note": r.get("user_note"),
        "hidden": bool(r.get("hidden")),
        "duplicate_of": r.get("duplicate_of"),
        "favorite": favorite,
        "association": assoc,
        "sender_id": sender_id,
    }


def media_payloads(conn: sqlite3.Connection, rows: Sequence[sqlite3.Row]) -> list[dict[str, Any]]:
    ids = [r["id"] for r in rows]
    favs = favorites_set(conn, "media", ids)
    msg_ids = [r["message_id"] for r in rows if r["message_id"]]
    senders: dict[int, str] = {}
    for i in range(0, len(msg_ids), 500):
        chunk = msg_ids[i:i + 500]
        senders.update({r[0]: r[1] for r in conn.execute(
            f"SELECT id, sender_id FROM messages WHERE id IN ({','.join('?' * len(chunk))})", chunk)})
    return [media_payload(r, favorite=str(r["id"]) in favs, sender_id=senders.get(r["message_id"])) for r in rows]


def message_payloads(conn: sqlite3.Connection, rows: Sequence[sqlite3.Row], *, with_media: bool = True) -> list[dict]:
    if not rows:
        return []
    ids = [r["id"] for r in rows]
    favs = favorites_set(conn, "message", ids)
    media_by_msg: dict[int, dict] = {}
    if with_media:
        for i in range(0, len(ids), 500):
            chunk = ids[i:i + 500]
            mrows = conn.execute(
                f"SELECT {MEDIA_COLUMNS} FROM media WHERE message_id IN ({','.join('?' * len(chunk))}) AND hidden = 0",
                chunk,
            ).fetchall()
            for p in media_payloads(conn, mrows):
                media_by_msg[p["association"]["message_id"]] = p
    reply_ids = [r["reply_to_message_id"] for r in rows if r["reply_to_message_id"]]
    replies: dict[int, dict] = {}
    if reply_ids:
        for r in conn.execute(
            f"SELECT id, sender_id, msg_type, text FROM messages WHERE id IN ({','.join('?' * len(reply_ids))})",
            reply_ids,
        ):
            replies[r["id"]] = {"id": r["id"], "sender_id": r["sender_id"], "type": r["msg_type"],
                                "text": (r["text"] or "")[:80]}
    out = []
    for r in rows:
        meta = loads(r["metadata"], {}) or {}
        out.append({
            "id": r["id"],
            "ts": r["ts"],
            "day": r["day"],
            "sender_id": r["sender_id"],
            "sender_name": r["sender_name"],
            "type": r["msg_type"],
            "text": r["text"],
            "media_ref": r["media_ref"],
            "media": media_by_msg.get(r["id"]),
            "reply_to": replies.get(r["reply_to_message_id"]),
            "duration": meta.get("duration"),
            "favorite": str(r["id"]) in favs,
        })
    return out


MESSAGE_COLUMNS = """id, ts, day, sender_id, sender_name, msg_type, text, media_ref, metadata, reply_to_message_id"""
