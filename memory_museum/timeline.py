"""Timeline queries: year/month overview, curated day cards, full day view."""

from __future__ import annotations

import re
import sqlite3
from datetime import date, datetime, timedelta
from typing import Any

from memory_museum.serialize import (
    MEDIA_COLUMNS,
    MESSAGE_COLUMNS,
    favorites_set,
    media_payloads,
    message_payloads,
)
from memory_museum.timeutil import TS_FORMAT

NOT_HIDDEN_DAY = "day NOT IN (SELECT day FROM hidden_days)"
VISUAL_MEDIA = "media_type IN ('image','video')"
MEDIA_VISIBLE = "hidden = 0 AND duplicate_of IS NULL AND status = 'ok'"

# A day enters the curated Memory Timeline if it has any photo/video/voice,
# a substantial conversation, or the user favorited it.
CURATED_MIN_MESSAGES = 30

_ONLY_SYMBOLS = re.compile(r"^[\W_\d\s]+$", re.UNICODE)


def _curated_clause() -> str:
    return (f"(photo_count + video_count + voice_count > 0 OR msg_count >= {CURATED_MIN_MESSAGES} "
            "OR day IN (SELECT ref FROM favorites WHERE kind = 'day') "
            "OR day IN (SELECT start_day FROM moments WHERE start_day IS NOT NULL))")


def years_overview(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    months: dict[int, list[dict]] = {}
    for r in conn.execute(
        f"""SELECT year, month, COUNT(*) AS days, SUM(msg_count) AS messages, SUM(photo_count) AS photos,
                   SUM(video_count) AS videos, SUM(voice_count) AS voices, SUM({_curated_clause()}) AS memory_days
            FROM day_summary WHERE {NOT_HIDDEN_DAY} GROUP BY year, month ORDER BY year, month"""
    ):
        months.setdefault(r["year"], []).append(dict(r))
    covers = month_covers(conn)
    out = []
    for year, ms in months.items():
        for m in ms:
            m["cover"] = covers.get(f"{year:04d}-{m['month']:02d}")
        out.append({
            "year": year,
            "days": sum(m["days"] for m in ms),
            "messages": sum(m["messages"] for m in ms),
            "photos": sum(m["photos"] for m in ms),
            "videos": sum(m["videos"] for m in ms),
            "voices": sum(m["voices"] for m in ms),
            "months": ms,
        })
    return out


def month_covers(conn: sqlite3.Connection) -> dict[str, str]:
    """One representative thumbnail per month: a favorited photo if any, else the first photo of the richest day."""
    out: dict[str, str] = {}
    rows = conn.execute(
        f"""SELECT substr(m.day, 1, 7) AS ym, m.id,
                   (m.id IN (SELECT CAST(ref AS INTEGER) FROM favorites WHERE kind = 'media')) AS fav,
                   COALESCE(d.score, 0) AS score
            FROM media m LEFT JOIN day_summary d ON d.day = m.day
            WHERE m.media_type = 'image' AND m.thumb_path IS NOT NULL AND m.hidden = 0
              AND m.duplicate_of IS NULL AND m.status = 'ok' AND m.day NOT IN (SELECT day FROM hidden_days)
            ORDER BY ym, fav DESC, score DESC, m.ts"""
    )
    for r in rows:
        out.setdefault(r["ym"], f"/api/media/{r['id']}/thumb")
    return out


def _is_excerpt_worthy(text: str | None) -> bool:
    if not text:
        return False
    t = text.strip()
    return 4 <= len(t) <= 120 and not _ONLY_SYMBOLS.match(t) and not t.lower().startswith(("http://", "https://"))


def select_excerpts(conn: sqlite3.Connection, day: str, n: int = 3) -> list[dict]:
    """Pick a few real messages spread across the day. Favorited messages come first.

    This is a readability heuristic (length, spread over the day), not an
    interpretation of what mattered.
    """
    rows = conn.execute(
        f"SELECT {MESSAGE_COLUMNS} FROM messages WHERE day = ? AND msg_type = 'text' AND hidden = 0 "
        "ORDER BY ts, id LIMIT 3000",
        (day,),
    ).fetchall()
    worthy = [r for r in rows if _is_excerpt_worthy(r["text"])]
    if not worthy:
        worthy = [r for r in rows if r["text"]]
    favs = favorites_set(conn, "message", [r["id"] for r in worthy])
    chosen = [r for r in worthy if str(r["id"]) in favs][:n]
    remaining = [r for r in worthy if str(r["id"]) not in favs]
    need = n - len(chosen)
    if need > 0 and remaining:
        size = max(1, len(remaining) // need)
        for i in range(0, len(remaining), size):
            chunk = remaining[i:i + size]
            best = max(chunk, key=lambda r: min(len(r["text"]), 36) - max(0, len(r["text"]) - 60) * 0.5)
            chosen.append(best)
            if len(chosen) >= n:
                break
    chosen.sort(key=lambda r: (r["ts"], r["id"]))
    return message_payloads(conn, chosen, with_media=False)


def _stats(row: sqlite3.Row | None) -> dict[str, Any]:
    if row is None:
        return {"messages": 0, "photos": 0, "videos": 0, "voices": 0, "audio_seconds": 0,
                "longest_session_minutes": 0, "first_ts": None, "last_ts": None, "score": 0}
    return {"messages": row["msg_count"], "photos": row["photo_count"], "videos": row["video_count"],
            "voices": row["voice_count"], "audio_seconds": round(row["audio_seconds"] or 0, 1),
            "longest_session_minutes": row["longest_session_minutes"], "first_ts": row["first_ts"],
            "last_ts": row["last_ts"], "score": row["score"]}


def _day_media(conn: sqlite3.Connection, day: str, kinds: str, limit: int | None) -> list[dict]:
    """Media captured on this day, plus media sent in chat on this day."""
    lim = f" LIMIT {int(limit)}" if limit else ""
    rows = conn.execute(
        f"""SELECT {MEDIA_COLUMNS} FROM media
            WHERE {MEDIA_VISIBLE} AND media_type IN ({kinds})
              AND (day = ? OR message_id IN (SELECT id FROM messages WHERE day = ?))
            ORDER BY ts, id{lim}""",
        (day, day),
    ).fetchall()
    return media_payloads(conn, rows)


def _moments_for_day(conn: sqlite3.Connection, day: str) -> list[dict]:
    return [dict(r) for r in conn.execute(
        """SELECT id, title FROM moments WHERE (start_day <= ? AND COALESCE(end_day, start_day) >= ?)
           OR id IN (SELECT moment_id FROM moment_items mi JOIN messages m ON mi.kind = 'message' AND mi.ref = m.id
                     WHERE m.day = ?)
           OR id IN (SELECT moment_id FROM moment_items mi JOIN media md ON mi.kind = 'media' AND mi.ref = md.id
                     WHERE md.day = ?)
           ORDER BY start_day""",
        (day, day, day, day),
    )]


def day_card(conn: sqlite3.Connection, row: sqlite3.Row, *, favorite_days: set[str] | None = None) -> dict[str, Any]:
    day = row["day"]
    return {
        "day": day,
        "stats": _stats(row),
        "excerpts": select_excerpts(conn, day),
        "media": _day_media(conn, day, "'image','video'", 6),
        "voices": _day_media(conn, day, "'voice','audio'", 3),
        "favorite": day in (favorite_days if favorite_days is not None else favorites_set(conn, "day", [day])),
        "moments": _moments_for_day(conn, day),
    }


def timeline_page(
    conn: sqlite3.Connection,
    *,
    cursor: str | None = None,
    limit: int = 12,
    order: str = "asc",
    mode: str = "curated",
    year: int | None = None,
    month: int | None = None,
) -> dict[str, Any]:
    limit = max(1, min(limit, 50))
    desc = order == "desc"
    where = [NOT_HIDDEN_DAY]
    params: list[Any] = []
    if mode == "curated":
        where.append(_curated_clause())
    if year:
        where.append("year = ?")
        params.append(year)
    if month:
        where.append("month = ?")
        params.append(month)
    if cursor:
        where.append("day < ?" if desc else "day > ?")
        params.append(cursor)
    rows = conn.execute(
        f"SELECT * FROM day_summary WHERE {' AND '.join(where)} ORDER BY day {'DESC' if desc else 'ASC'} LIMIT ?",
        [*params, limit + 1],
    ).fetchall()
    has_more = len(rows) > limit
    rows = rows[:limit]
    favs = favorites_set(conn, "day", [r["day"] for r in rows])
    items = [day_card(conn, r, favorite_days=favs) for r in rows]
    return {"items": items, "next_cursor": rows[-1]["day"] if has_more and rows else None}


def neighbour_days(conn: sqlite3.Connection, day: str) -> dict[str, str | None]:
    prev = conn.execute(f"SELECT day FROM day_summary WHERE day < ? AND {NOT_HIDDEN_DAY} ORDER BY day DESC LIMIT 1",
                        (day,)).fetchone()
    nxt = conn.execute(f"SELECT day FROM day_summary WHERE day > ? AND {NOT_HIDDEN_DAY} ORDER BY day ASC LIMIT 1",
                       (day,)).fetchone()
    return {"prev_day": prev[0] if prev else None, "next_day": nxt[0] if nxt else None}


def day_messages(conn: sqlite3.Connection, day: str, *, cursor: str | None = None, limit: int = 200) -> dict[str, Any]:
    limit = max(1, min(limit, 500))
    params: list[Any] = [day]
    extra = ""
    if cursor:
        ts, _, mid = cursor.partition("|")
        extra = " AND (ts > ? OR (ts = ? AND id > ?))"
        params += [ts, ts, int(mid or 0)]
    rows = conn.execute(
        f"SELECT {MESSAGE_COLUMNS} FROM messages WHERE day = ? AND hidden = 0{extra} ORDER BY ts, id LIMIT ?",
        [*params, limit + 1],
    ).fetchall()
    has_more = len(rows) > limit
    rows = rows[:limit]
    return {
        "items": message_payloads(conn, rows),
        "next_cursor": f"{rows[-1]['ts']}|{rows[-1]['id']}" if has_more and rows else None,
    }


def day_detail(conn: sqlite3.Connection, day: str, *, message_limit: int = 200) -> dict[str, Any] | None:
    try:
        date.fromisoformat(day)
    except ValueError:
        return None
    hidden = conn.execute("SELECT 1 FROM hidden_days WHERE day = ?", (day,)).fetchone() is not None
    row = conn.execute("SELECT * FROM day_summary WHERE day = ?", (day,)).fetchone()
    detail = {
        "day": day,
        "hidden": hidden,
        "stats": _stats(row),
        "favorite": bool(favorites_set(conn, "day", [day])),
        "moments": _moments_for_day(conn, day),
        **neighbour_days(conn, day),
    }
    if hidden:
        detail.update(media=[], voices=[], messages={"items": [], "next_cursor": None}, excerpts=[])
        return detail
    detail["media"] = _day_media(conn, day, "'image','video'", None)
    detail["voices"] = _day_media(conn, day, "'voice','audio'", None)
    detail["excerpts"] = select_excerpts(conn, day) if row else []
    detail["messages"] = day_messages(conn, day, limit=message_limit)
    return detail


def context_around(conn: sqlite3.Connection, ts: str, *, before: int = 12, after: int = 12,
                   window_hours: int = 6) -> list[dict]:
    """Real messages surrounding a moment (e.g. when a photo was taken)."""
    t = datetime.strptime(ts, TS_FORMAT)
    lo = (t - timedelta(hours=window_hours)).strftime(TS_FORMAT)
    hi = (t + timedelta(hours=window_hours)).strftime(TS_FORMAT)
    prev = conn.execute(
        f"SELECT {MESSAGE_COLUMNS} FROM messages WHERE ts <= ? AND ts >= ? AND hidden = 0 AND {NOT_HIDDEN_DAY} "
        "ORDER BY ts DESC, id DESC LIMIT ?",
        (ts, lo, before),
    ).fetchall()
    nxt = conn.execute(
        f"SELECT {MESSAGE_COLUMNS} FROM messages WHERE ts > ? AND ts <= ? AND hidden = 0 AND {NOT_HIDDEN_DAY} "
        "ORDER BY ts, id LIMIT ?",
        (ts, hi, after),
    ).fetchall()
    return message_payloads(conn, list(reversed(prev)) + list(nxt))
