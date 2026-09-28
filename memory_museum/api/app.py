"""FastAPI application: JSON API under /api plus the built frontend.

Binds to 127.0.0.1 by default. Nothing here contacts the internet.
"""

from __future__ import annotations

import io
import re
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterator, Literal

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field

from memory_museum import __version__, curation, library, security, timeline
from memory_museum.association import link_manually, reset_manual
from memory_museum.config import FRONTEND_DIST, Paths
from memory_museum.db import open_db
from memory_museum.random_day import pick_random_day
from memory_museum.serialize import MESSAGE_COLUMNS
from memory_museum.settings import effective_copy, get_settings, update_settings
from memory_museum.stats import compute_stats

OPEN_PATHS = {"/api/health", "/api/lock/status", "/api/lock/unlock"}
DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class PinBody(BaseModel):
    pin: str


class ChangePinBody(BaseModel):
    current: str | None = None
    new: str | None = None


class HiddenBody(BaseModel):
    hidden: bool


class MediaPatch(BaseModel):
    title: str | None = None
    note: str | None = None
    hidden: bool | None = None
    ts: str | None = None


class LinkBody(BaseModel):
    message_id: int | None


class MomentItem(BaseModel):
    kind: Literal["message", "media"]
    ref: int


class MomentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    start_day: str | None = None
    end_day: str | None = None
    cover_media_id: int | None = None
    items: list[MomentItem] = []


class MomentPatch(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    start_day: str | None = None
    end_day: str | None = None
    cover_media_id: int | None = None


def create_app(paths: Paths, *, frontend_dist: Path | None = FRONTEND_DIST) -> FastAPI:
    paths.ensure()
    setup = open_db(paths.db)
    app = FastAPI(title="Our Memory Museum", version=__version__, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.paths = paths
    app.state.sessions = security.SessionStore()
    app.state.lock_enabled = security.lock_enabled(setup)
    app.state.idle_timeout = security.idle_timeout_seconds(setup)
    setup.close()

    def get_conn() -> Iterator[sqlite3.Connection]:
        conn = open_db(paths.db, check_same_thread=False)
        try:
            yield conn
        finally:
            conn.close()

    Conn = Depends(get_conn)

    @app.middleware("http")
    async def gate(request: Request, call_next):
        path = request.url.path
        if path.startswith("/api/") and path not in OPEN_PATHS and app.state.lock_enabled:
            token = request.cookies.get(security.COOKIE_NAME)
            if not app.state.sessions.touch(token, app.state.idle_timeout):
                return JSONResponse({"detail": "locked"}, status_code=401, headers={"Cache-Control": "no-store"})
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        if path.startswith("/api/") and "Cache-Control" not in response.headers:
            response.headers["Cache-Control"] = "no-store"
        return response

    # ------------------------------------------------------------ lock
    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True, "version": __version__}

    @app.get("/api/lock/status")
    def lock_status(request: Request, conn: sqlite3.Connection = Conn) -> dict:
        token = request.cookies.get(security.COOKIE_NAME)
        unlocked = (not app.state.lock_enabled) or app.state.sessions.touch(token, app.state.idle_timeout)
        s = get_settings(conn)
        return {
            "enabled": app.state.lock_enabled,
            "unlocked": unlocked,
            "auto_lock_minutes": s["auto_lock_minutes"],
            "language": s["language"],
            "theme": s["theme"],
        }

    def _set_cookie(response: Response, token: str) -> None:
        response.set_cookie(security.COOKIE_NAME, token, httponly=True, samesite="strict", path="/")

    @app.post("/api/lock/unlock")
    def unlock(body: PinBody, response: Response, conn: sqlite3.Connection = Conn) -> dict:
        if not app.state.lock_enabled:
            return {"unlocked": True}
        wait = app.state.sessions.throttled()
        if wait:
            raise HTTPException(429, f"too many attempts, wait {int(wait) + 1}s")
        if not security.check_pin(conn, body.pin):
            app.state.sessions.record_failure()
            time.sleep(0.4)
            raise HTTPException(403, "wrong PIN")
        _set_cookie(response, app.state.sessions.create())
        return {"unlocked": True}

    @app.post("/api/lock/lock")
    def lock_now(request: Request, response: Response) -> dict:
        app.state.sessions.revoke(request.cookies.get(security.COOKIE_NAME))
        response.delete_cookie(security.COOKIE_NAME, path="/")
        return {"locked": app.state.lock_enabled}

    @app.post("/api/lock/pin")
    def change_pin(body: ChangePinBody, response: Response, conn: sqlite3.Connection = Conn) -> dict:
        if app.state.lock_enabled and not security.check_pin(conn, body.current or ""):
            raise HTTPException(403, "current PIN is wrong")
        try:
            security.set_pin(conn, body.new or None)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        app.state.lock_enabled = security.lock_enabled(conn)
        app.state.sessions.revoke_all()
        if app.state.lock_enabled:
            _set_cookie(response, app.state.sessions.create())
        return {"enabled": app.state.lock_enabled}

    # ------------------------------------------------------------ settings / copy
    @app.get("/api/copy")
    def copy_(conn: sqlite3.Connection = Conn) -> dict:
        return effective_copy(conn)

    @app.get("/api/settings")
    def settings_(conn: sqlite3.Connection = Conn) -> dict:
        s = get_settings(conn)
        s["participants_detected"] = [dict(r) for r in conn.execute(
            "SELECT id, display_name, message_count FROM participants ORDER BY message_count DESC")]
        s["hidden_days"] = [r[0] for r in conn.execute("SELECT day FROM hidden_days ORDER BY day")]
        s["lock_enabled"] = app.state.lock_enabled
        return s

    @app.patch("/api/settings")
    def patch_settings(patch: dict[str, Any], conn: sqlite3.Connection = Conn) -> dict:
        try:
            update_settings(conn, patch)
        except KeyError as e:
            raise HTTPException(400, str(e)) from e
        app.state.idle_timeout = security.idle_timeout_seconds(conn)
        return settings_(conn)

    @app.post("/api/settings/avatar/{sender_id}")
    async def upload_avatar(sender_id: str, file: UploadFile = File(...), conn: sqlite3.Connection = Conn) -> dict:
        raw = await file.read(15 * 1024 * 1024 + 1)
        if len(raw) > 15 * 1024 * 1024:
            raise HTTPException(413, "image too large")
        try:
            with Image.open(io.BytesIO(raw)) as img:
                img = ImageOps.exif_transpose(img).convert("RGB")
                img = ImageOps.fit(img, (320, 320), Image.Resampling.LANCZOS)
                out = paths.avatars / f"{_safe_name(sender_id)}.jpg"
                img.save(out, "JPEG", quality=88)  # re-encoding drops EXIF (incl. GPS)
        except (UnidentifiedImageError, OSError) as e:
            raise HTTPException(400, "not a readable image") from e
        s = get_settings(conn)
        participants = dict(s.get("participants") or {})
        entry = dict(participants.get(sender_id) or {})
        entry["avatar"] = f"/api/avatars/{sender_id}?v={int(time.time())}"
        participants[sender_id] = entry
        update_settings(conn, {"participants": participants})
        return {"avatar": entry["avatar"]}

    @app.get("/api/avatars/{sender_id}")
    def avatar(sender_id: str) -> FileResponse:
        p = paths.avatars / f"{_safe_name(sender_id)}.jpg"
        if not p.exists():
            raise HTTPException(404, "no avatar")
        return FileResponse(p, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})

    # ------------------------------------------------------------ overview & timeline
    @app.get("/api/overview")
    def overview(conn: sqlite3.Connection = Conn) -> dict:
        return library.overview(conn)

    @app.get("/api/timeline/years")
    def years(conn: sqlite3.Connection = Conn) -> list:
        return timeline.years_overview(conn)

    @app.get("/api/timeline")
    def timeline_(
        cursor: str | None = None,
        limit: int = Query(12, ge=1, le=50),
        order: Literal["asc", "desc"] = "asc",
        mode: Literal["curated", "all"] = "curated",
        year: int | None = None,
        month: int | None = Query(None, ge=1, le=12),
        conn: sqlite3.Connection = Conn,
    ) -> dict:
        return timeline.timeline_page(conn, cursor=cursor, limit=limit, order=order, mode=mode, year=year, month=month)

    def _check_day(day: str) -> str:
        if not DAY_RE.match(day):
            raise HTTPException(400, "day must be YYYY-MM-DD")
        return day

    @app.get("/api/days/{day}")
    def day(day: str, conn: sqlite3.Connection = Conn) -> dict:
        detail = timeline.day_detail(conn, _check_day(day))
        if detail is None:
            raise HTTPException(400, "invalid date")
        return detail

    @app.get("/api/days/{day}/messages")
    def day_messages(day: str, cursor: str | None = None, limit: int = Query(200, ge=1, le=500),
                     conn: sqlite3.Connection = Conn) -> dict:
        return timeline.day_messages(conn, _check_day(day), cursor=cursor, limit=limit)

    @app.put("/api/days/{day}/hidden")
    def hide_day(day: str, body: HiddenBody, conn: sqlite3.Connection = Conn) -> dict:
        curation.set_day_hidden(conn, _check_day(day), body.hidden)
        return {"day": day, "hidden": body.hidden}

    @app.get("/api/random-day")
    def random_day(exclude: str | None = None, mode: Literal["weighted", "uniform"] | None = None,
                   conn: sqlite3.Connection = Conn) -> dict:
        picked = pick_random_day(conn, exclude=exclude, mode=mode)
        if picked is None:
            return {"day": None}
        return timeline.day_detail(conn, picked, message_limit=80)

    # ------------------------------------------------------------ media
    @app.get("/api/sounds")
    def sounds(cursor: str | None = None, limit: int = Query(30, ge=1, le=100), favorites: bool = False,
               sender: str | None = None, order: Literal["asc", "desc"] = "asc",
               conn: sqlite3.Connection = Conn) -> dict:
        return library.sounds(conn, cursor=cursor, limit=limit, favorites=favorites, sender=sender, order=order)

    @app.get("/api/gallery/months")
    def gallery_months(conn: sqlite3.Connection = Conn) -> list:
        return library.gallery_months(conn)

    @app.get("/api/gallery")
    def gallery(cursor: str | None = None, limit: int = Query(60, ge=1, le=200),
                kind: Literal["all", "image", "video"] = "all", month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
                favorites: bool = False, order: Literal["asc", "desc"] = "asc",
                conn: sqlite3.Connection = Conn) -> dict:
        return library.gallery(conn, cursor=cursor, limit=limit, kind=kind, month=month, favorites=favorites,
                               order=order)

    def _media_row(conn: sqlite3.Connection, media_id: int) -> sqlite3.Row:
        r = conn.execute("SELECT id, path, thumb_path, playable_path, media_type, ext, status FROM media WHERE id = ?",
                         (media_id,)).fetchone()
        if not r:
            raise HTTPException(404, "media not found")
        return r

    @app.get("/api/media/{media_id}")
    def media(media_id: int, conn: sqlite3.Connection = Conn) -> dict:
        d = library.media_detail(conn, media_id)
        if not d:
            raise HTTPException(404, "media not found")
        return d

    @app.get("/api/media/{media_id}/file")
    def media_file(media_id: int, conn: sqlite3.Connection = Conn) -> FileResponse:
        r = _media_row(conn, media_id)
        # only paths recorded by the importer are ever served (no user-supplied paths)
        p = Path(r["playable_path"]) if r["playable_path"] and Path(r["playable_path"]).exists() else Path(r["path"])
        if not p.exists():
            raise HTTPException(404, "the original file is no longer on disk")
        return FileResponse(p, media_type=_mime(p), headers={"Cache-Control": "private, max-age=3600"})

    @app.get("/api/media/{media_id}/thumb")
    def media_thumb(media_id: int, conn: sqlite3.Connection = Conn) -> FileResponse:
        r = _media_row(conn, media_id)
        if not r["thumb_path"] or not Path(r["thumb_path"]).exists():
            raise HTTPException(404, "no thumbnail")
        return FileResponse(r["thumb_path"], media_type="image/jpeg",
                            headers={"Cache-Control": "private, max-age=604800"})

    @app.patch("/api/media/{media_id}")
    def patch_media(media_id: int, patch: MediaPatch, conn: sqlite3.Connection = Conn) -> dict:
        try:
            out = curation.update_media(conn, media_id, patch.model_dump(exclude_unset=True))
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        if out is None:
            raise HTTPException(404, "media not found")
        return out

    @app.put("/api/media/{media_id}/link")
    def link_media(media_id: int, body: LinkBody, conn: sqlite3.Connection = Conn) -> dict:
        _media_row(conn, media_id)
        if body.message_id is not None and not conn.execute("SELECT 1 FROM messages WHERE id = ?",
                                                            (body.message_id,)).fetchone():
            raise HTTPException(404, "message not found")
        link_manually(conn, media_id, body.message_id)
        return library.media_detail(conn, media_id)

    @app.delete("/api/media/{media_id}/link")
    def reset_link(media_id: int, conn: sqlite3.Connection = Conn) -> dict:
        _media_row(conn, media_id)
        reset_manual(conn, media_id)
        return library.media_detail(conn, media_id)

    @app.get("/api/media/{media_id}/context")
    def media_context(media_id: int, conn: sqlite3.Connection = Conn) -> dict:
        d = library.media_detail(conn, media_id)
        if not d:
            raise HTTPException(404, "media not found")
        anchor = (d.get("message") or {}).get("ts") or d["ts"]
        return {"media": d, "anchor_ts": anchor, "anchor_message_id": d["association"]["message_id"]
                if d.get("association") else None,
                "messages": timeline.context_around(conn, anchor) if anchor else []}

    @app.get("/api/media/{media_id}/candidates")
    def media_candidates(media_id: int, conn: sqlite3.Connection = Conn) -> list:
        _media_row(conn, media_id)
        return library.link_candidates(conn, media_id)

    # ------------------------------------------------------------ messages / search
    @app.get("/api/messages/{message_id}/context")
    def message_context(message_id: int, conn: sqlite3.Connection = Conn) -> dict:
        r = conn.execute("SELECT ts FROM messages WHERE id = ?", (message_id,)).fetchone()
        if not r:
            raise HTTPException(404, "message not found")
        return {"anchor_ts": r["ts"], "anchor_message_id": message_id,
                "messages": timeline.context_around(conn, r["ts"]) if r["ts"] else []}

    @app.patch("/api/messages/{message_id}")
    def patch_message(message_id: int, body: HiddenBody, conn: sqlite3.Connection = Conn) -> dict:
        if not curation.set_message_hidden(conn, message_id, body.hidden):
            raise HTTPException(404, "message not found")
        return {"id": message_id, "hidden": body.hidden}

    @app.get("/api/search")
    def search(q: str = Query(..., min_length=1, max_length=100), cursor: str | None = None,
               conn: sqlite3.Connection = Conn) -> dict:
        return library.search_messages(conn, q, cursor=cursor)

    # ------------------------------------------------------------ favorites
    @app.get("/api/favorites")
    def favorites(kind: Literal["message", "media", "day", "moment"] | None = None,
                  conn: sqlite3.Connection = Conn) -> list:
        return curation.list_favorites(conn, kind)

    @app.put("/api/favorites/{kind}/{ref}")
    def add_favorite(kind: Literal["message", "media", "day", "moment"], ref: str,
                     conn: sqlite3.Connection = Conn) -> dict:
        _check_ref(kind, ref)
        curation.set_favorite(conn, kind, ref, True)
        return {"kind": kind, "ref": ref, "favorite": True}

    @app.delete("/api/favorites/{kind}/{ref}")
    def remove_favorite(kind: Literal["message", "media", "day", "moment"], ref: str,
                        conn: sqlite3.Connection = Conn) -> dict:
        curation.set_favorite(conn, kind, ref, False)
        return {"kind": kind, "ref": ref, "favorite": False}

    def _check_ref(kind: str, ref: str) -> None:
        if kind == "day":
            _check_day(ref)
        elif not ref.isdigit():
            raise HTTPException(400, "ref must be a numeric id")

    # ------------------------------------------------------------ moments
    @app.get("/api/moments")
    def moments(conn: sqlite3.Connection = Conn) -> list:
        return curation.list_moments(conn)

    @app.post("/api/moments", status_code=201)
    def create_moment(body: MomentCreate, conn: sqlite3.Connection = Conn) -> dict:
        try:
            return curation.create_moment(conn, body.model_dump())
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    @app.get("/api/moments/{moment_id}")
    def moment(moment_id: int, conn: sqlite3.Connection = Conn) -> dict:
        m = curation.get_moment(conn, moment_id)
        if not m:
            raise HTTPException(404, "moment not found")
        return m

    @app.patch("/api/moments/{moment_id}")
    def patch_moment(moment_id: int, body: MomentPatch, conn: sqlite3.Connection = Conn) -> dict:
        try:
            m = curation.update_moment(conn, moment_id, body.model_dump(exclude_unset=True))
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        if not m:
            raise HTTPException(404, "moment not found")
        return m

    @app.delete("/api/moments/{moment_id}")
    def delete_moment(moment_id: int, conn: sqlite3.Connection = Conn) -> dict:
        if not curation.delete_moment(conn, moment_id):
            raise HTTPException(404, "moment not found")
        return {"deleted": moment_id}

    @app.post("/api/moments/{moment_id}/items")
    def add_item(moment_id: int, item: MomentItem, conn: sqlite3.Connection = Conn) -> dict:
        if not conn.execute("SELECT 1 FROM moments WHERE id = ?", (moment_id,)).fetchone():
            raise HTTPException(404, "moment not found")
        try:
            curation.add_moment_item(conn, moment_id, item.kind, item.ref)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        return curation.get_moment(conn, moment_id)

    @app.delete("/api/moments/{moment_id}/items/{kind}/{ref}")
    def remove_item(moment_id: int, kind: Literal["message", "media"], ref: int,
                    conn: sqlite3.Connection = Conn) -> dict:
        curation.remove_moment_item(conn, moment_id, kind, ref)
        m = curation.get_moment(conn, moment_id)
        if not m:
            raise HTTPException(404, "moment not found")
        return m

    # ------------------------------------------------------------ stats & review
    @app.get("/api/stats")
    def stats(conn: sqlite3.Connection = Conn) -> dict:
        return compute_stats(conn)

    @app.get("/api/review/summary")
    def review_summary(conn: sqlite3.Connection = Conn) -> dict:
        return library.review_summary(conn)

    @app.get("/api/review/media")
    def review_media(filter: str = "low", cursor: str | None = None, limit: int = Query(40, ge=1, le=100),
                     conn: sqlite3.Connection = Conn) -> dict:
        try:
            return library.review_items(conn, filter, cursor=cursor, limit=limit)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    @app.get("/api/review/messages/{message_id}")
    def review_message(message_id: int, conn: sqlite3.Connection = Conn) -> dict:
        r = conn.execute(f"SELECT {MESSAGE_COLUMNS}, hidden FROM messages WHERE id = ?", (message_id,)).fetchone()
        if not r:
            raise HTTPException(404, "message not found")
        return {"id": r["id"], "hidden": bool(r["hidden"]), "day": r["day"], "text": r["text"]}

    # ------------------------------------------------------------ frontend
    if frontend_dist and (frontend_dist / "index.html").exists():
        assets = frontend_dist / "assets"
        if assets.exists():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")
        index_html = frontend_dist / "index.html"

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str):
            if full_path.startswith("api/"):
                raise HTTPException(404, "not found")
            candidate = (frontend_dist / full_path).resolve()
            if full_path and candidate.is_file() and candidate.is_relative_to(frontend_dist.resolve()):
                return FileResponse(candidate)
            return FileResponse(index_html, headers={"Cache-Control": "no-cache"})
    else:
        @app.get("/", include_in_schema=False)
        def no_frontend():
            return JSONResponse({
                "message": "API is running, but the frontend has not been built yet.",
                "fix": "cd frontend && npm install && npm run build   (then restart the server)",
            })

    return app


_MIME = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp", ".gif": "image/gif",
    ".bmp": "image/bmp", ".heic": "image/heic", ".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/mp4",
    ".aac": "audio/aac", ".ogg": "audio/ogg", ".opus": "audio/ogg", ".flac": "audio/flac", ".amr": "audio/amr",
    ".mp4": "video/mp4", ".m4v": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm", ".3gp": "video/3gpp",
    ".mkv": "video/x-matroska", ".avi": "video/x-msvideo",
}


def _mime(p: Path) -> str:
    return _MIME.get(p.suffix.lower(), "application/octet-stream")


def _safe_name(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_\-]", "_", s)[:64] or "_"
