"""User curation: favorites, Memory Moments, hiding, titles/notes, manual dates."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from memory_museum.association import adopt_chat_time
from memory_museum.index import refresh_after_edit
from memory_museum.serialize import MEDIA_COLUMNS, MESSAGE_COLUMNS, media_payloads, message_payloads
from memory_museum.timeutil import TimestampError, fmt, parse_timestamp

FAVORITE_KINDS = ("message", "media", "day", "moment")
MOMENT_ITEM_KINDS = ("message", "media")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------- favorites

def set_favorite(conn: sqlite3.Connection, kind: str, ref: str, on: bool) -> None:
    if kind not in FAVORITE_KINDS:
        raise ValueError(f"unknown favorite kind {kind!r}")
    if on:
        conn.execute("INSERT OR IGNORE INTO favorites(kind, ref, created_at) VALUES (?, ?, ?)", (kind, str(ref), _now()))
    else:
        conn.execute("DELETE FROM favorites WHERE kind = ? AND ref = ?", (kind, str(ref)))
    conn.commit()


def list_favorites(conn: sqlite3.Connection, kind: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
    params: list[Any] = []
    where = ""
    if kind:
        where = "WHERE kind = ?"
        params.append(kind)
    favs = conn.execute(f"SELECT kind, ref, created_at FROM favorites {where} ORDER BY created_at DESC LIMIT ?",
                        [*params, limit]).fetchall()
    by_kind: dict[str, list[str]] = {}
    for f in favs:
        by_kind.setdefault(f["kind"], []).append(f["ref"])

    resolved: dict[tuple[str, str], Any] = {}
    if by_kind.get("media"):
        ids = [int(x) for x in by_kind["media"] if x.isdigit()]
        rows = conn.execute(f"SELECT {MEDIA_COLUMNS} FROM media WHERE id IN ({','.join('?' * len(ids))}) AND hidden = 0",
                            ids).fetchall() if ids else []
        for p in media_payloads(conn, rows):
            resolved[("media", str(p["id"]))] = p
    if by_kind.get("message"):
        ids = [int(x) for x in by_kind["message"] if x.isdigit()]
        rows = conn.execute(
            f"SELECT {MESSAGE_COLUMNS} FROM messages WHERE id IN ({','.join('?' * len(ids))}) AND hidden = 0", ids
        ).fetchall() if ids else []
        for p in message_payloads(conn, rows):
            resolved[("message", str(p["id"]))] = p
    for d in by_kind.get("day", []):
        row = conn.execute("SELECT * FROM day_summary WHERE day = ?", (d,)).fetchone()
        hidden = conn.execute("SELECT 1 FROM hidden_days WHERE day = ?", (d,)).fetchone()
        if row and not hidden:
            from memory_museum.timeline import day_card

            resolved[("day", d)] = day_card(conn, row, favorite_days={d})
    for m in by_kind.get("moment", []):
        if m.isdigit():
            mo = get_moment(conn, int(m), with_items=False)
            if mo:
                resolved[("moment", m)] = mo

    out = []
    for f in favs:
        item = resolved.get((f["kind"], f["ref"]))
        if item is not None:
            out.append({"kind": f["kind"], "ref": f["ref"], "created_at": f["created_at"], "item": item})
    return out


# ---------------------------------------------------------------- hiding

def set_day_hidden(conn: sqlite3.Connection, day: str, hidden: bool) -> None:
    if hidden:
        conn.execute("INSERT OR IGNORE INTO hidden_days(day) VALUES (?)", (day,))
    else:
        conn.execute("DELETE FROM hidden_days WHERE day = ?", (day,))
    conn.commit()
    refresh_after_edit(conn, [])


def set_message_hidden(conn: sqlite3.Connection, message_id: int, hidden: bool) -> bool:
    row = conn.execute("SELECT day FROM messages WHERE id = ?", (message_id,)).fetchone()
    if not row:
        return False
    conn.execute("UPDATE messages SET hidden = ? WHERE id = ?", (1 if hidden else 0, message_id))
    conn.commit()
    refresh_after_edit(conn, [row["day"]])
    return True


def update_media(conn: sqlite3.Connection, media_id: int, patch: dict[str, Any]) -> dict | None:
    row = conn.execute("SELECT id, day, ts FROM media WHERE id = ?", (media_id,)).fetchone()
    if not row:
        return None
    touched_days = {row["day"]}
    if "title" in patch:
        conn.execute("UPDATE media SET user_title = ? WHERE id = ?", ((patch["title"] or "").strip() or None, media_id))
    if "note" in patch:
        conn.execute("UPDATE media SET user_note = ? WHERE id = ?", ((patch["note"] or "").strip() or None, media_id))
    if "hidden" in patch:
        conn.execute("UPDATE media SET hidden = ? WHERE id = ?", (1 if patch["hidden"] else 0, media_id))
    if "ts" in patch:
        if patch["ts"] in (None, ""):
            conn.execute("""UPDATE media SET ts = original_ts, day = substr(original_ts, 1, 10),
                            ts_source = original_ts_source WHERE id = ?""", (media_id,))
            adopt_chat_time(conn, media_id)
        else:
            try:
                ts = fmt(parse_timestamp(patch["ts"]))
            except TimestampError as e:
                raise ValueError(f"invalid date: {e}") from e
            conn.execute("UPDATE media SET ts = ?, day = ?, ts_source = 'manual' WHERE id = ?", (ts, ts[:10], media_id))
    conn.commit()
    new_day = conn.execute("SELECT day FROM media WHERE id = ?", (media_id,)).fetchone()["day"]
    touched_days.add(new_day)
    if {"hidden", "ts"} & patch.keys():
        refresh_after_edit(conn, touched_days)
    r = conn.execute(f"SELECT {MEDIA_COLUMNS} FROM media WHERE id = ?", (media_id,)).fetchone()
    return media_payloads(conn, [r])[0]


# ---------------------------------------------------------------- moments

def _moment_row(conn: sqlite3.Connection, r: sqlite3.Row) -> dict[str, Any]:
    counts = {k: 0 for k in MOMENT_ITEM_KINDS}
    for c in conn.execute("SELECT kind, COUNT(*) AS n FROM moment_items WHERE moment_id = ? GROUP BY kind", (r["id"],)):
        counts[c["kind"]] = c["n"]
    cover = None
    cover_id = r["cover_media_id"] or (conn.execute(
        """SELECT mi.ref FROM moment_items mi JOIN media m ON m.id = mi.ref
           WHERE mi.moment_id = ? AND mi.kind = 'media' AND m.thumb_path IS NOT NULL AND m.hidden = 0
           ORDER BY mi.position LIMIT 1""", (r["id"],)).fetchone() or [None])[0]
    if cover_id:
        mr = conn.execute(f"SELECT {MEDIA_COLUMNS} FROM media WHERE id = ?", (cover_id,)).fetchone()
        if mr:
            cover = media_payloads(conn, [mr])[0]
    fav = conn.execute("SELECT 1 FROM favorites WHERE kind = 'moment' AND ref = ?", (str(r["id"]),)).fetchone()
    return {
        "id": r["id"], "title": r["title"], "description": r["description"], "start_day": r["start_day"],
        "end_day": r["end_day"], "cover": cover, "counts": counts, "favorite": fav is not None,
        "created_at": r["created_at"], "updated_at": r["updated_at"],
    }


def list_moments(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM moments ORDER BY COALESCE(start_day, created_at), id").fetchall()
    return [_moment_row(conn, r) for r in rows]


def get_moment(conn: sqlite3.Connection, moment_id: int, *, with_items: bool = True) -> dict[str, Any] | None:
    r = conn.execute("SELECT * FROM moments WHERE id = ?", (moment_id,)).fetchone()
    if not r:
        return None
    out = _moment_row(conn, r)
    if with_items:
        items = conn.execute("SELECT kind, ref FROM moment_items WHERE moment_id = ? ORDER BY position, ref",
                             (moment_id,)).fetchall()
        msg_ids = [i["ref"] for i in items if i["kind"] == "message"]
        media_ids = [i["ref"] for i in items if i["kind"] == "media"]
        msgs = conn.execute(f"SELECT {MESSAGE_COLUMNS} FROM messages WHERE id IN ({','.join('?' * len(msg_ids))}) "
                            "ORDER BY ts, id", msg_ids).fetchall() if msg_ids else []
        media = conn.execute(f"SELECT {MEDIA_COLUMNS} FROM media WHERE id IN ({','.join('?' * len(media_ids))}) "
                             "AND hidden = 0 ORDER BY ts, id", media_ids).fetchall() if media_ids else []
        out["messages"] = message_payloads(conn, msgs)
        out["media"] = media_payloads(conn, media)
    return out


def _check_day(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        return fmt(parse_timestamp(str(value)))[:10]
    except TimestampError as e:
        raise ValueError(f"invalid date {value!r}") from e


def create_moment(conn: sqlite3.Connection, data: dict[str, Any]) -> dict[str, Any]:
    title = (data.get("title") or "").strip()
    if not title:
        raise ValueError("a moment needs a title")
    now = _now()
    cur = conn.execute(
        "INSERT INTO moments(title, description, start_day, end_day, cover_media_id, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (title, (data.get("description") or "").strip() or None, _check_day(data.get("start_day")),
         _check_day(data.get("end_day")), data.get("cover_media_id"), now, now),
    )
    mid = int(cur.lastrowid)
    for pos, item in enumerate(data.get("items") or []):
        add_moment_item(conn, mid, item["kind"], int(item["ref"]), position=pos, commit=False)
    conn.commit()
    return get_moment(conn, mid)


def update_moment(conn: sqlite3.Connection, moment_id: int, patch: dict[str, Any]) -> dict[str, Any] | None:
    if not conn.execute("SELECT 1 FROM moments WHERE id = ?", (moment_id,)).fetchone():
        return None
    fields = {}
    if "title" in patch:
        t = (patch["title"] or "").strip()
        if not t:
            raise ValueError("a moment needs a title")
        fields["title"] = t
    if "description" in patch:
        fields["description"] = (patch["description"] or "").strip() or None
    for k in ("start_day", "end_day"):
        if k in patch:
            fields[k] = _check_day(patch[k])
    if "cover_media_id" in patch:
        fields["cover_media_id"] = patch["cover_media_id"]
    if fields:
        fields["updated_at"] = _now()
        conn.execute(f"UPDATE moments SET {', '.join(f'{k} = ?' for k in fields)} WHERE id = ?",
                     [*fields.values(), moment_id])
        conn.commit()
    return get_moment(conn, moment_id)


def delete_moment(conn: sqlite3.Connection, moment_id: int) -> bool:
    cur = conn.execute("DELETE FROM moments WHERE id = ?", (moment_id,))
    conn.execute("DELETE FROM favorites WHERE kind = 'moment' AND ref = ?", (str(moment_id),))
    conn.commit()
    return cur.rowcount > 0


def add_moment_item(conn: sqlite3.Connection, moment_id: int, kind: str, ref: int, *, position: int | None = None,
                    commit: bool = True) -> None:
    if kind not in MOMENT_ITEM_KINDS:
        raise ValueError(f"unknown item kind {kind!r}")
    table = "messages" if kind == "message" else "media"
    if not conn.execute(f"SELECT 1 FROM {table} WHERE id = ?", (ref,)).fetchone():
        raise ValueError(f"{kind} {ref} does not exist")
    if position is None:
        position = (conn.execute("SELECT COALESCE(MAX(position), -1) + 1 FROM moment_items WHERE moment_id = ?",
                                 (moment_id,)).fetchone()[0])
    conn.execute("INSERT OR IGNORE INTO moment_items(moment_id, kind, ref, position) VALUES (?, ?, ?, ?)",
                 (moment_id, kind, ref, position))
    conn.execute("UPDATE moments SET updated_at = ? WHERE id = ?", (_now(), moment_id))
    if commit:
        conn.commit()


def remove_moment_item(conn: sqlite3.Connection, moment_id: int, kind: str, ref: int) -> None:
    conn.execute("DELETE FROM moment_items WHERE moment_id = ? AND kind = ? AND ref = ?", (moment_id, kind, ref))
    conn.commit()
