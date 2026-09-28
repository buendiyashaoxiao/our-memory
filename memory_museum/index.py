"""Derived indexes: per-day summaries and cached statistics.

``day_summary`` makes the timeline, Random Day and stats fast on very large
archives: they read a few thousand day rows instead of scanning every message.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Iterable

from memory_museum.db import dumps
from memory_museum.timeutil import TS_FORMAT

SESSION_GAP_MINUTES = 15


def day_score(row: dict) -> float:
    """Heuristic 'how much happened' score, used only for ordering and weighting.

    It never claims emotional meaning; it just prefers days with more activity.
    """
    return round(
        min(row["msg_count"], 400) / 40
        + min(row["text_chars"] / 2000, 5)
        + min(row["photo_count"] * 1.5, 12)
        + min(row["video_count"] * 2.5, 10)
        + min(row["voice_count"] * 1.5, 9)
        + min(row["longest_session_minutes"] / 60, 3),
        3,
    )


def _filter(days: Iterable[str] | None, column: str = "day") -> tuple[str, list[str]]:
    if days is None:
        return "", []
    days = sorted(set(d for d in days if d))
    if not days:
        return " AND 0", []
    return f" AND {column} IN ({','.join('?' * len(days))})", days


def build_day_summary(conn: sqlite3.Connection, days: Iterable[str] | None = None) -> int:
    days = list(days) if days is not None else None
    where, params = _filter(days)
    conn.execute(f"DELETE FROM day_summary WHERE 1{where}", params)

    rows: dict[str, dict] = {}

    def row(day: str) -> dict:
        if day not in rows:
            rows[day] = {"day": day, "year": int(day[:4]), "month": int(day[5:7]), "msg_count": 0, "text_count": 0,
                         "text_chars": 0, "photo_count": 0, "video_count": 0, "voice_count": 0,
                         "audio_seconds": 0.0, "first_ts": None, "last_ts": None, "longest_session_minutes": 0}
        return rows[day]

    for r in conn.execute(
        f"""SELECT day, COUNT(*) AS n, SUM(msg_type = 'text') AS tn,
                   SUM(CASE WHEN msg_type = 'text' THEN length(text) ELSE 0 END) AS chars,
                   MIN(ts) AS first_ts, MAX(ts) AS last_ts
            FROM messages WHERE day IS NOT NULL AND hidden = 0{where} GROUP BY day""",
        params,
    ):
        d = row(r["day"])
        d.update(msg_count=r["n"], text_count=r["tn"] or 0, text_chars=r["chars"] or 0,
                 first_ts=r["first_ts"], last_ts=r["last_ts"])

    for r in conn.execute(
        f"""SELECT day, media_type, COUNT(*) AS n, SUM(COALESCE(duration, 0)) AS secs
            FROM media WHERE day IS NOT NULL AND hidden = 0 AND duplicate_of IS NULL AND status = 'ok'{where}
            GROUP BY day, media_type""",
        params,
    ):
        d = row(r["day"])
        if r["media_type"] == "image":
            d["photo_count"] += r["n"]
        elif r["media_type"] == "video":
            d["video_count"] += r["n"]
        elif r["media_type"] in ("voice", "audio"):
            d["voice_count"] += r["n"]
            d["audio_seconds"] += r["secs"] or 0

    # longest continuous conversation per day (gaps <= SESSION_GAP_MINUTES)
    cur_day, start, prev = None, None, None
    gap = SESSION_GAP_MINUTES * 60
    for r in conn.execute(f"SELECT day, ts FROM messages WHERE day IS NOT NULL AND hidden = 0{where} ORDER BY ts", params):
        t = datetime.strptime(r["ts"], TS_FORMAT).timestamp()
        if r["day"] != cur_day or prev is None or t - prev > gap:
            if cur_day is not None and start is not None and cur_day in rows:
                rows[cur_day]["longest_session_minutes"] = max(rows[cur_day]["longest_session_minutes"],
                                                               int((prev - start) / 60))
            cur_day, start = r["day"], t
        prev = t
    if cur_day is not None and start is not None and cur_day in rows:
        rows[cur_day]["longest_session_minutes"] = max(rows[cur_day]["longest_session_minutes"], int((prev - start) / 60))

    for d in rows.values():
        d["score"] = day_score(d)
    conn.executemany(
        """INSERT INTO day_summary(day, year, month, msg_count, text_count, text_chars, photo_count, video_count,
               voice_count, audio_seconds, first_ts, last_ts, longest_session_minutes, score)
           VALUES (:day, :year, :month, :msg_count, :text_count, :text_chars, :photo_count, :video_count,
               :voice_count, :audio_seconds, :first_ts, :last_ts, :longest_session_minutes, :score)""",
        list(rows.values()),
    )
    conn.commit()
    return len(rows)


def invalidate_stats(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM stats_cache")
    conn.commit()


def refresh_after_edit(conn: sqlite3.Connection, days: Iterable[str | None]) -> None:
    """Recompute summaries for days touched by a hide/unhide/date edit."""
    build_day_summary(conn, [d for d in days if d])
    invalidate_stats(conn)


def build_index(conn: sqlite3.Connection) -> dict:
    from memory_museum.stats import compute_stats

    n = build_day_summary(conn)
    stats = compute_stats(conn, use_cache=False)
    conn.execute("ANALYZE")
    conn.commit()
    return {"days": n, "stats_cached": bool(stats)}


def cache_put(conn: sqlite3.Connection, key: str, value) -> None:
    conn.execute(
        "INSERT INTO stats_cache(key, value, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
        (key, dumps(value), datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()
