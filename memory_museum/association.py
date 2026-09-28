"""Chat <-> media association.

1. **Exact** — a message's media reference names a file we imported.
2. **Fuzzy** — a media-type message ("[图片]") without a resolvable reference
   is paired with an unlinked file of the same kind taken close in time.

Confidence levels: ``exact`` > ``high`` > ``medium`` > ``low``.
``low`` matches are *never* applied; they are stored only as a suggestion for
the review screen. Manual links/unlinks (``association_locked``) are never
overwritten.
"""

from __future__ import annotations

import bisect
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from memory_museum.timeutil import TS_FORMAT

LEVELS = ("low", "medium", "high", "exact")
TRUSTED_SOURCES = {"exif", "media_meta", "filename", "manual"}
WEAK_SOURCES = {"mtime", "filename_date"}

HIGH_WINDOW = 120  # seconds
MEDIUM_WINDOW = 600
LOW_WINDOW = 1800
AMBIGUITY_GAP = 60

COMPATIBLE = {
    "image": ("image",),
    "video": ("video",),
    "voice": ("voice", "audio"),
    "audio": ("voice", "audio"),
}


@dataclass
class AssociationReport:
    exact: int = 0
    high: int = 0
    medium: int = 0
    low_suggestions: int = 0
    manual: int = 0
    unassociated_media: int = 0
    unresolved_refs: int = 0
    media_messages_without_file: int = 0
    unresolved_examples: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def _ts(s: str) -> float:
    return datetime.strptime(s, TS_FORMAT).timestamp()


def downgrade(level: str, steps: int = 1) -> str:
    return LEVELS[max(0, LEVELS.index(level) - steps)]


def score_time_match(delta_s: float, ts_source: str | None, runner_up_delta: float | None) -> str | None:
    """Confidence for a time-proximity match, or None if too far apart."""
    delta_s = abs(delta_s)
    if delta_s <= HIGH_WINDOW:
        level = "high"
    elif delta_s <= MEDIUM_WINDOW:
        level = "medium"
    elif delta_s <= LOW_WINDOW:
        level = "low"
    else:
        return None
    if ts_source in WEAK_SOURCES or ts_source is None:
        level = downgrade(level)
    if runner_up_delta is not None and abs(runner_up_delta) - delta_s < AMBIGUITY_GAP:
        level = downgrade(level)
    return level


def _ref_key(ref: str) -> str:
    return re.split(r"[\\/]", ref.strip())[-1].split("?")[0].lower()


def associate(conn: sqlite3.Connection) -> AssociationReport:
    rep = AssociationReport()
    # reset automatic decisions so the engine is idempotent
    conn.execute("""UPDATE media SET ts = original_ts, day = substr(original_ts, 1, 10), ts_source = original_ts_source
                    WHERE ts_source = 'chat' AND association_locked = 0""")
    conn.execute("""UPDATE media SET message_id = NULL, association_method = NULL, association_confidence = NULL,
                    suggested_message_id = NULL WHERE association_locked = 0""")

    taken_messages: set[int] = {
        r[0] for r in conn.execute("SELECT message_id FROM media WHERE association_locked = 1 AND message_id IS NOT NULL")
    }
    rep.manual = len(taken_messages)
    locked_media = {r[0] for r in conn.execute("SELECT id FROM media WHERE association_locked = 1")}

    by_name: dict[str, list[tuple[int, str | None]]] = defaultdict(list)
    by_stem: dict[str, list[tuple[int, str | None]]] = defaultdict(list)
    content: dict[int, tuple[str | None, bool]] = {}  # id -> (hash, is_duplicate_copy)
    for r in conn.execute("SELECT id, original_filename, ts, hash, duplicate_of FROM media"):
        if r["id"] in locked_media:
            continue
        name = r["original_filename"].lower()
        by_name[name].append((r["id"], r["ts"]))
        by_stem[name.rsplit(".", 1)[0]].append((r["id"], r["ts"]))
        content[r["id"]] = (r["hash"], r["duplicate_of"] is not None)

    assignments: list[tuple[int, int, str, str]] = []  # media_id, message_id, method, confidence
    taken_media: set[int] = set()

    # 1. exact filename matches
    for m in conn.execute("SELECT id, ts, media_ref FROM messages WHERE media_ref IS NOT NULL ORDER BY id"):
        if m["id"] in taken_messages:
            continue
        key = _ref_key(m["media_ref"])
        cands = [c for c in by_name.get(key, []) if c[0] not in taken_media]
        method = "exact_filename"
        if not cands and "." not in key:
            cands = [c for c in by_stem.get(key, []) if c[0] not in taken_media]
            method = "exact_stem"
        if not cands:
            if not by_name.get(key):
                rep.unresolved_refs += 1
                if len(rep.unresolved_examples) < 20:
                    rep.unresolved_examples.append(m["media_ref"])
            continue
        hashes = {content[c[0]][0] for c in cands}
        if len(cands) > 1 and len(hashes) == 1 and None not in hashes:
            # several byte-identical copies (e.g. a backup folder): same photo, so still exact
            cands = sorted(cands, key=lambda c: content[c[0]][1])[:1]
        if len(cands) == 1:
            media_id, conf = cands[0][0], "exact"
        else:
            # same filename in several folders: pick the closest in time, but say we're less sure
            if m["ts"]:
                mt = _ts(m["ts"])
                cands.sort(key=lambda c: abs(_ts(c[1]) - mt) if c[1] else float("inf"))
            media_id, conf, method = cands[0][0], "high", "filename_time"
        taken_media.add(media_id)
        taken_messages.add(m["id"])
        assignments.append((media_id, m["id"], method, conf))

    # 2. fuzzy time proximity for media-type messages without a usable reference
    msgs_by_kind: dict[str, list[tuple[float, int]]] = defaultdict(list)
    for m in conn.execute(
        "SELECT id, ts, msg_type FROM messages WHERE msg_type IN ('image','video','voice','audio') "
        "AND ts IS NOT NULL AND hidden = 0"
    ):
        if m["id"] not in taken_messages:
            msgs_by_kind[m["msg_type"]].append((_ts(m["ts"]), m["id"]))
    for lst in msgs_by_kind.values():
        lst.sort()

    candidates: list[tuple[float, int, int, str, float | None, str | None]] = []
    for md in conn.execute(
        "SELECT id, ts, ts_source, media_type FROM media WHERE ts IS NOT NULL AND status = 'ok' "
        "AND duplicate_of IS NULL AND association_locked = 0"
    ):
        if md["id"] in taken_media:
            continue
        t = _ts(md["ts"])
        near: list[tuple[float, int]] = []
        for kind in COMPATIBLE.get(md["media_type"], ()):
            lst = msgs_by_kind.get(kind, [])
            lo = bisect.bisect_left(lst, (t - LOW_WINDOW, -1))
            hi = bisect.bisect_right(lst, (t + LOW_WINDOW, float("inf")))
            near += [(abs(mt - t), mid) for mt, mid in lst[lo:hi]]
        if not near:
            continue
        near.sort()
        for i, (delta, mid) in enumerate(near):
            runner_up = near[i + 1][0] if i + 1 < len(near) else None
            if i > 0:
                runner_up = near[0][0] if runner_up is None else min(runner_up, near[0][0])
            candidates.append((delta, md["id"], mid, md["ts_source"], runner_up, md["media_type"]))

    candidates.sort()
    suggested: dict[int, int] = {}
    for delta, media_id, msg_id, source, runner_up, _ in candidates:
        if media_id in taken_media or msg_id in taken_messages:
            continue
        level = score_time_match(delta, source, runner_up)
        if level is None:
            continue
        if level == "low":
            suggested.setdefault(media_id, msg_id)
            continue
        taken_media.add(media_id)
        taken_messages.add(msg_id)
        assignments.append((media_id, msg_id, "time_proximity", level))

    conn.executemany(
        "UPDATE media SET message_id = ?, association_method = ?, association_confidence = ? WHERE id = ?",
        [(msg, method, conf, media) for media, msg, method, conf in assignments],
    )
    conn.executemany(
        "UPDATE media SET suggested_message_id = ?, association_method = 'time_proximity', "
        "association_confidence = 'low' WHERE id = ? AND message_id IS NULL",
        [(msg, media) for media, msg in suggested.items() if media not in taken_media],
    )
    counts = Counter(conf for *_, conf in assignments)
    rep.exact, rep.high, rep.medium = counts["exact"], counts["high"], counts["medium"]
    rep.low_suggestions = sum(1 for m in suggested if m not in taken_media)

    adopt_chat_time(conn)
    conn.execute(
        """UPDATE media SET media_type = 'voice' WHERE media_type = 'audio' AND message_id IN
           (SELECT id FROM messages WHERE msg_type = 'voice')"""
    )
    rep.unassociated_media = conn.execute(
        "SELECT COUNT(*) FROM media WHERE message_id IS NULL AND duplicate_of IS NULL"
    ).fetchone()[0]
    rep.media_messages_without_file = conn.execute(
        """SELECT COUNT(*) FROM messages m WHERE m.msg_type IN ('image','video','voice','audio')
           AND NOT EXISTS (SELECT 1 FROM media WHERE media.message_id = m.id)"""
    ).fetchone()[0]
    conn.commit()
    return rep


def adopt_chat_time(conn: sqlite3.Connection, media_id: int | None = None) -> None:
    """Media with no trustworthy capture time adopts the time it was sent in chat."""
    only = " AND id = ?" if media_id is not None else ""
    conn.execute(
        f"""
        UPDATE media SET
            ts = (SELECT ts FROM messages WHERE messages.id = media.message_id),
            day = (SELECT day FROM messages WHERE messages.id = media.message_id),
            ts_source = 'chat'
        WHERE message_id IS NOT NULL AND association_confidence IN ('exact', 'high')
          AND (ts IS NULL OR ts_source IN ('mtime', 'filename_date'))
          AND (SELECT ts FROM messages WHERE messages.id = media.message_id) IS NOT NULL{only}
        """,
        (media_id,) if media_id is not None else (),
    )


def link_manually(conn: sqlite3.Connection, media_id: int, message_id: int | None) -> None:
    """User decision: link (or with None, unlink) and lock against automatic changes."""
    if message_id is None:
        conn.execute(
            """UPDATE media SET message_id = NULL, suggested_message_id = NULL, association_method = 'manual',
               association_confidence = NULL, association_locked = 1 WHERE id = ?""",
            (media_id,),
        )
    else:
        conn.execute("""UPDATE media SET message_id = NULL, association_locked = 0, association_method = NULL
                        WHERE message_id = ? AND id != ? AND association_locked = 0""", (message_id, media_id))
        conn.execute(
            """UPDATE media SET message_id = ?, suggested_message_id = NULL, association_method = 'manual',
               association_confidence = 'exact', association_locked = 1 WHERE id = ?""",
            (message_id, media_id),
        )
    conn.commit()


def reset_manual(conn: sqlite3.Connection, media_id: int) -> None:
    conn.execute("UPDATE media SET association_locked = 0 WHERE id = ?", (media_id,))
    conn.commit()
