"""Random Day / Take Me Back: pick a day that actually has something in it."""

from __future__ import annotations

import random
import sqlite3
from typing import Any

from memory_museum.settings import get_settings


def candidate_days(conn: sqlite3.Connection, min_messages: int = 5) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT day, msg_count, photo_count, video_count, voice_count, text_chars, longest_session_minutes
           FROM day_summary
           WHERE day NOT IN (SELECT day FROM hidden_days)
             AND (msg_count >= ? OR photo_count + video_count + voice_count > 0)
           ORDER BY day""",
        (min_messages,),
    ).fetchall()


def day_weight(row: sqlite3.Row | dict, cfg: dict[str, Any]) -> float:
    if cfg.get("mode") == "uniform":
        return 1.0
    return (
        1.0
        + float(cfg.get("photo", 1.0)) * min(row["photo_count"], 10) * 0.6
        + float(cfg.get("voice", 1.0)) * min(row["voice_count"], 6) * 0.8
        + float(cfg.get("video", 1.0)) * min(row["video_count"], 4) * 1.2
        + float(cfg.get("conversation", 1.0)) * min(row["msg_count"] / 40, 5)
    )


def pick_random_day(
    conn: sqlite3.Connection,
    *,
    rng: random.Random | None = None,
    exclude: str | None = None,
    mode: str | None = None,
) -> str | None:
    cfg = dict(get_settings(conn)["random_day"])
    if mode:
        cfg["mode"] = mode
    rows = candidate_days(conn, int(cfg.get("min_messages", 5)))
    if not rows:
        # nothing "meaningful": fall back to any day that has activity at all
        rows = candidate_days(conn, 1)
    pool = [r for r in rows if r["day"] != exclude] or rows
    if not pool:
        return None
    rng = rng or random.SystemRandom()
    weights = [day_weight(r, cfg) for r in pool]
    return rng.choices(pool, weights=weights, k=1)[0]["day"]
