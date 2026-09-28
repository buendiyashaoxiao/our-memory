"""Media-centric queries: Sound Museum, gallery, review queue, search, overview."""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Any

from memory_museum.serialize import MEDIA_COLUMNS, MESSAGE_COLUMNS, media_payloads, message_payloads
from memory_museum.settings import display_names

VISIBLE = ("hidden = 0 AND duplicate_of IS NULL AND status = 'ok' "
           "AND (day IS NULL OR day NOT IN (SELECT day FROM hidden_days))")


def _cursor_clause(cursor: str | None, desc: bool) -> tuple[str, list[Any]]:
    if not cursor:
        return "", []
    ts, _, mid = cursor.partition("|")
    op = "<" if desc else ">"
    return f" AND (ts {op} ? OR (ts = ? AND id {op} ?))", [ts, ts, int(mid or 0)]


def _page(rows: list[sqlite3.Row], limit: int) -> tuple[list[sqlite3.Row], str | None]:
    has_more = len(rows) > limit
    rows = rows[:limit]
    return rows, (f"{rows[-1]['ts']}|{rows[-1]['id']}" if has_more and rows else None)


def sounds(conn: sqlite3.Connection, *, cursor: str | None = None, limit: int = 30, favorites: bool = False,
           sender: str | None = None, order: str = "asc") -> dict[str, Any]:
    limit = max(1, min(limit, 100))
    desc = order == "desc"
    where = f"media_type IN ('voice','audio') AND ts IS NOT NULL AND {VISIBLE}"
    params: list[Any] = []
    if favorites:
        where += " AND id IN (SELECT CAST(ref AS INTEGER) FROM favorites WHERE kind = 'media')"
    if sender:
        where += " AND message_id IN (SELECT id FROM messages WHERE sender_id = ?)"
        params.append(sender)
    extra, cparams = _cursor_clause(cursor, desc)
    direction = "DESC" if desc else "ASC"
    rows = conn.execute(f"SELECT {MEDIA_COLUMNS} FROM media WHERE {where}{extra} ORDER BY ts {direction}, id {direction} "
                        "LIMIT ?", [*params, *cparams, limit + 1]).fetchall()
    rows, next_cursor = _page(rows, limit)
    items = media_payloads(conn, rows)
    for item in items:
        item["context"] = voice_context(conn, item)
    total = conn.execute(f"SELECT COUNT(*), COALESCE(SUM(duration), 0) FROM media WHERE {where}", params).fetchone()
    return {"items": items, "next_cursor": next_cursor, "total": total[0], "total_seconds": round(total[1], 1)}


def voice_context(conn: sqlite3.Connection, item: dict[str, Any]) -> list[dict]:
    """The text messages sent right before and after a voice message (within 30 minutes)."""
    anchor_id = item["association"]["message_id"] if item.get("association") else None
    ts = item["ts"]
    if not ts:
        return []
    before = conn.execute(
        f"""SELECT {MESSAGE_COLUMNS} FROM messages WHERE msg_type = 'text' AND hidden = 0 AND ts <= ?
            AND ts >= strftime('%Y-%m-%dT%H:%M:%S', ?, '-30 minutes') AND id != COALESCE(?, -1)
            ORDER BY ts DESC, id DESC LIMIT 1""",
        (ts, ts, anchor_id),
    ).fetchall()
    after = conn.execute(
        f"""SELECT {MESSAGE_COLUMNS} FROM messages WHERE msg_type = 'text' AND hidden = 0 AND ts > ?
            AND ts <= strftime('%Y-%m-%dT%H:%M:%S', ?, '+30 minutes') ORDER BY ts, id LIMIT 1""",
        (ts, ts),
    ).fetchall()
    return message_payloads(conn, list(before) + list(after), with_media=False)


def gallery_months(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(
        f"""SELECT substr(day, 1, 7) AS month, SUM(media_type = 'image') AS photos, SUM(media_type = 'video') AS videos
            FROM media WHERE media_type IN ('image','video') AND day IS NOT NULL AND {VISIBLE}
            GROUP BY month ORDER BY month"""
    )]


def gallery(conn: sqlite3.Connection, *, cursor: str | None = None, limit: int = 60, kind: str = "all",
            month: str | None = None, favorites: bool = False, order: str = "asc") -> dict[str, Any]:
    limit = max(1, min(limit, 200))
    desc = order == "desc"
    kinds = {"image": "('image')", "video": "('video')"}.get(kind, "('image','video')")
    where = f"media_type IN {kinds} AND ts IS NOT NULL AND {VISIBLE}"
    params: list[Any] = []
    if month:
        y, m = (int(x) for x in month.split("-")[:2])
        start = date(y, m, 1).isoformat()
        end = date(y + (m == 12), m % 12 + 1, 1).isoformat()
        where += " AND day >= ? AND day < ?"
        params += [start, end]
    if favorites:
        where += " AND id IN (SELECT CAST(ref AS INTEGER) FROM favorites WHERE kind = 'media')"
    extra, cparams = _cursor_clause(cursor, desc)
    direction = "DESC" if desc else "ASC"
    rows = conn.execute(f"SELECT {MEDIA_COLUMNS} FROM media WHERE {where}{extra} ORDER BY ts {direction}, id {direction} "
                        "LIMIT ?", [*params, *cparams, limit + 1]).fetchall()
    rows, next_cursor = _page(rows, limit)
    return {"items": media_payloads(conn, rows), "next_cursor": next_cursor}


def media_detail(conn: sqlite3.Connection, media_id: int) -> dict[str, Any] | None:
    r = conn.execute(f"SELECT {MEDIA_COLUMNS}, rel_path, codec, metadata, original_ts, original_ts_source "
                     "FROM media WHERE id = ?", (media_id,)).fetchone()
    if not r:
        return None
    out = media_payloads(conn, [r])[0]
    out["rel_path"] = r["rel_path"]
    out["codec"] = r["codec"]
    out["original_ts"] = r["original_ts"]
    out["original_ts_source"] = r["original_ts_source"]
    for key in ("message_id", "suggested_message_id"):
        mid = r[key]
        if mid:
            mrow = conn.execute(f"SELECT {MESSAGE_COLUMNS} FROM messages WHERE id = ?", (mid,)).fetchone()
            out[key.replace("_id", "")] = message_payloads(conn, [mrow], with_media=False)[0] if mrow else None
    return out


REVIEW_FILTERS = {
    "low": "message_id IS NULL AND suggested_message_id IS NOT NULL AND duplicate_of IS NULL",
    "medium": "association_confidence = 'medium' AND message_id IS NOT NULL",
    "unlinked": "message_id IS NULL AND duplicate_of IS NULL AND status = 'ok' AND hidden = 0",
    "problems": "status != 'ok'",
    "hidden": "hidden = 1",
    "manual": "association_locked = 1",
    "duplicates": "duplicate_of IS NOT NULL",
}


def review_summary(conn: sqlite3.Connection) -> dict[str, int]:
    return {k: conn.execute(f"SELECT COUNT(*) FROM media WHERE {w}").fetchone()[0] for k, w in REVIEW_FILTERS.items()}


def review_items(conn: sqlite3.Connection, filter_: str, *, cursor: str | None = None, limit: int = 40) -> dict:
    where = REVIEW_FILTERS.get(filter_)
    if where is None:
        raise ValueError(f"unknown filter {filter_!r}")
    limit = max(1, min(limit, 100))
    offset = int(cursor or 0)
    rows = conn.execute(f"SELECT id FROM media WHERE {where} ORDER BY ts, id LIMIT ? OFFSET ?",
                        (limit + 1, offset)).fetchall()
    has_more = len(rows) > limit
    items = [media_detail(conn, r["id"]) for r in rows[:limit]]
    return {"items": items, "next_cursor": str(offset + limit) if has_more else None}


def link_candidates(conn: sqlite3.Connection, media_id: int, hours: int = 3, limit: int = 40) -> list[dict]:
    r = conn.execute("SELECT ts FROM media WHERE id = ?", (media_id,)).fetchone()
    if not r or not r["ts"]:
        return []
    rows = conn.execute(
        f"""SELECT {MESSAGE_COLUMNS} FROM messages WHERE ts IS NOT NULL AND hidden = 0
            AND ts BETWEEN strftime('%Y-%m-%dT%H:%M:%S', ?, ?) AND strftime('%Y-%m-%dT%H:%M:%S', ?, ?)
            ORDER BY abs(julianday(ts) - julianday(?)), id LIMIT ?""",
        (r["ts"], f"-{hours} hours", r["ts"], f"+{hours} hours", r["ts"], limit),
    ).fetchall()
    return message_payloads(conn, sorted(rows, key=lambda x: (x["ts"], x["id"])))


def search_messages(conn: sqlite3.Connection, q: str, *, limit: int = 50, cursor: str | None = None) -> dict:
    q = q.strip()
    if not q:
        return {"items": [], "next_cursor": None}
    limit = max(1, min(limit, 100))
    extra, cparams = _cursor_clause(cursor, True)
    like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    rows = conn.execute(
        f"""SELECT {MESSAGE_COLUMNS} FROM messages WHERE text LIKE ? ESCAPE '\\' AND hidden = 0 AND ts IS NOT NULL
            AND day NOT IN (SELECT day FROM hidden_days){extra} ORDER BY ts DESC, id DESC LIMIT ?""",
        [like, *cparams, limit + 1],
    ).fetchall()
    rows, next_cursor = _page(rows, limit)
    return {"items": message_payloads(conn, rows, with_media=False), "next_cursor": next_cursor}


def overview(conn: sqlite3.Connection, today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    t = conn.execute(
        """SELECT COUNT(*) AS days, COALESCE(SUM(msg_count), 0) AS messages, COALESCE(SUM(photo_count), 0) AS photos,
                  COALESCE(SUM(video_count), 0) AS videos, COALESCE(SUM(voice_count), 0) AS voices,
                  MIN(day) AS first_day, MAX(day) AS last_day
           FROM day_summary WHERE day NOT IN (SELECT day FROM hidden_days)"""
    ).fetchone()
    names = display_names(conn)
    participants = [{"id": r["id"], "name": names.get(r["id"], r["id"]), "messages": r["message_count"]}
                    for r in conn.execute("SELECT id, message_count FROM participants ORDER BY message_count DESC")]
    md = today.strftime("-%m-%d")
    on_this_day = [dict(r) for r in conn.execute(
        """SELECT day, msg_count, photo_count, voice_count, video_count FROM day_summary
           WHERE substr(day, 5) = ? AND day < ? AND day NOT IN (SELECT day FROM hidden_days)
             AND (msg_count >= 5 OR photo_count + video_count + voice_count > 0)
           ORDER BY day DESC""",
        (md, today.isoformat()),
    )]
    recent_cover = conn.execute(
        f"""SELECT id FROM media WHERE media_type = 'image' AND thumb_path IS NOT NULL AND {VISIBLE}
            AND id IN (SELECT CAST(ref AS INTEGER) FROM favorites WHERE kind = 'media') ORDER BY ts DESC LIMIT 1"""
    ).fetchone()
    return {
        "totals": dict(t),
        "participants": participants,
        "on_this_day": on_this_day,
        "cover": f"/api/media/{recent_cover[0]}/thumb" if recent_cover else None,
        "has_data": bool(t["days"]),
    }
