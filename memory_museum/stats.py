"""Relationship statistics computed only from imported data (no invented metrics)."""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Any

from memory_museum.db import loads
from memory_museum.index import cache_put
from memory_museum.settings import display_names
from memory_museum.textstats import count_words

VISIBLE_MSG = "hidden = 0 AND (day IS NULL OR day NOT IN (SELECT day FROM hidden_days))"
VISIBLE_DAY = "day NOT IN (SELECT day FROM hidden_days)"


def compute_stats(conn: sqlite3.Connection, *, use_cache: bool = True) -> dict[str, Any]:
    if use_cache:
        row = conn.execute("SELECT value FROM stats_cache WHERE key = 'overview'").fetchone()
        if row:
            cached = loads(row["value"])
            if cached:
                cached["names"] = display_names(conn)
                return cached

    q = lambda sql, *p: conn.execute(sql, p)  # noqa: E731
    totals = q(
        f"""SELECT COUNT(*) AS days, COALESCE(SUM(msg_count), 0) AS messages, COALESCE(SUM(photo_count), 0) AS photos,
                   COALESCE(SUM(video_count), 0) AS videos, COALESCE(SUM(voice_count), 0) AS voices,
                   COALESCE(SUM(audio_seconds), 0) AS voice_seconds, MIN(day) AS first_day, MAX(day) AS last_day
            FROM day_summary WHERE {VISIBLE_DAY}"""
    ).fetchone()
    out: dict[str, Any] = {"totals": dict(totals)}
    if totals["first_day"]:
        span = (date.fromisoformat(totals["last_day"]) - date.fromisoformat(totals["first_day"])).days + 1
        out["totals"]["span_days"] = span

    def top_day(col: str) -> dict | None:
        r = q(f"SELECT day, {col} AS value FROM day_summary WHERE {VISIBLE_DAY} AND {col} > 0 "
              f"ORDER BY {col} DESC, day LIMIT 1").fetchone()
        return dict(r) if r else None

    out["busiest_day"] = top_day("msg_count")
    out["longest_conversation_day"] = top_day("longest_session_minutes")
    out["most_photos_day"] = top_day("photo_count")

    months = [dict(r) for r in q(
        f"""SELECT printf('%04d-%02d', year, month) AS month, SUM(msg_count) AS messages,
                   SUM(photo_count) AS photos, SUM(voice_count) AS voices, SUM(video_count) AS videos
            FROM day_summary WHERE {VISIBLE_DAY} GROUP BY year, month ORDER BY year, month"""
    )]
    out["months"] = months
    out["busiest_month"] = max(months, key=lambda m: m["messages"]) if months else None

    hours = [0] * 24
    for r in q(f"SELECT hour, COUNT(*) AS n FROM messages WHERE hour IS NOT NULL AND {VISIBLE_MSG} GROUP BY hour"):
        hours[int(r["hour"])] = r["n"]
    out["hours"] = hours
    out["peak_hour"] = max(range(24), key=lambda h: hours[h]) if any(hours) else None

    weekdays = [0] * 7  # Monday first
    for r in q(f"SELECT strftime('%w', day) AS w, SUM(msg_count) AS n FROM day_summary WHERE {VISIBLE_DAY} GROUP BY w"):
        weekdays[(int(r["w"]) + 6) % 7] = r["n"]
    out["weekdays"] = weekdays

    out["by_sender"] = [dict(r) for r in q(
        f"""SELECT sender_id, COUNT(*) AS messages, SUM(msg_type = 'voice') AS voices, SUM(msg_type = 'image') AS photos
            FROM messages WHERE sender_id IS NOT NULL AND {VISIBLE_MSG} GROUP BY sender_id ORDER BY messages DESC"""
    )]
    lv = q(f"""SELECT id, day, duration FROM media WHERE media_type IN ('voice','audio') AND duration IS NOT NULL
               AND hidden = 0 AND duplicate_of IS NULL AND status = 'ok' AND (day IS NULL OR {VISIBLE_DAY})
               ORDER BY duration DESC LIMIT 1""").fetchone()
    out["longest_voice"] = dict(lv) if lv else None
    first = q(f"""SELECT id, ts, day, sender_id, text FROM messages WHERE msg_type = 'text' AND ts IS NOT NULL
                  AND {VISIBLE_MSG} ORDER BY ts, id LIMIT 1""").fetchone()
    out["first_message"] = dict(first) if first else None

    texts = (r[0] for r in conn.execute(f"SELECT text FROM messages WHERE msg_type = 'text' AND {VISIBLE_MSG}"))
    out["words"] = count_words(texts)

    cache_put(conn, "overview", out)
    out["names"] = display_names(conn)
    return out
