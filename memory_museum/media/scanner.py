"""Media import: walk folders, extract metadata in parallel, upsert into SQLite.

Original files are never copied or modified. Only small derived files
(thumbnails, transcoded audio) are written into the local cache directory.
"""

from __future__ import annotations

import os
import sqlite3
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from memory_museum.config import Paths
from memory_museum.db import dumps
from memory_museum.importer import SKIP_NAMES, finish_run, start_run
from memory_museum.media import ffmpeg
from memory_museum.media.metadata import classify, extract


@dataclass
class MediaReport:
    roots: list[str] = field(default_factory=list)
    files_seen: int = 0
    new: int = 0
    updated: int = 0
    unchanged: int = 0
    missing_marked: int = 0
    unsupported_files: int = 0
    by_type: Counter = field(default_factory=Counter)
    by_status: Counter = field(default_factory=Counter)
    ts_sources: Counter = field(default_factory=Counter)
    duplicates: int = 0
    problems: list[dict[str, Any]] = field(default_factory=list)
    ffmpeg: str | None = None
    ffprobe: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "roots": self.roots,
            "files_seen": self.files_seen,
            "new": self.new,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "missing_marked": self.missing_marked,
            "unsupported_files": self.unsupported_files,
            "by_type": dict(self.by_type),
            "by_status": dict(self.by_status),
            "ts_sources": dict(self.ts_sources),
            "duplicates": self.duplicates,
            "problems": self.problems[:200],
            "ffmpeg": self.ffmpeg,
            "ffprobe": self.ffprobe,
        }


_COLUMNS = (
    "path", "rel_path", "media_type", "original_filename", "ext", "size_bytes", "mtime", "hash", "ts", "day",
    "ts_source", "original_ts", "original_ts_source", "duration", "width", "height", "orientation", "codec",
    "metadata", "status", "error", "thumb_path", "playable_path", "waveform", "import_run",
)


def _row(info: dict[str, Any], run_id: int) -> dict[str, Any]:
    ts = info.get("ts")
    return {
        **{k: info.get(k) for k in _COLUMNS},
        "day": ts[:10] if ts else None,
        "original_ts": ts,
        "original_ts_source": info.get("ts_source"),
        "metadata": dumps(info.get("metadata") or {}),
        "waveform": dumps(info["waveform"]) if info.get("waveform") else None,
        "import_run": run_id,
    }


def iter_media_files(roots: Iterable[Path], report: MediaReport) -> list[tuple[Path, Path]]:
    out: list[tuple[Path, Path]] = []
    for root in roots:
        root = root.resolve()
        if root.is_file():
            out.append((root, root.parent))
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for name in filenames:
                if name.startswith(".") or name.lower() in SKIP_NAMES:
                    continue
                p = Path(dirpath) / name
                if classify(p) is None:
                    report.unsupported_files += 1
                    continue
                out.append((p, root))
    out.sort()
    return out


def import_media(
    conn: sqlite3.Connection,
    roots: Iterable[Path | str],
    paths: Paths,
    *,
    workers: int | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> MediaReport:
    paths.ensure()
    roots = [Path(r) for r in roots]
    report = MediaReport(roots=[str(r) for r in roots], **{k: v for k, v in ffmpeg.capabilities().items()})
    run_id = start_run(conn, "media", ";".join(report.roots))

    files = iter_media_files(roots, report)
    report.files_seen = len(files)
    existing = {
        r["path"]: (r["size_bytes"], r["mtime"], r["status"])
        for r in conn.execute("SELECT path, size_bytes, mtime, status FROM media")
    }

    todo: list[tuple[Path, Path]] = []
    for p, root in files:
        prev = existing.get(str(p.resolve()))
        if prev is not None:
            try:
                st = p.stat()
            except OSError:
                todo.append((p, root))
                continue
            if prev[0] == st.st_size and prev[1] == st.st_mtime and prev[2] != "missing":
                report.unchanged += 1
                continue
        todo.append((p, root))

    workers = workers or min(8, (os.cpu_count() or 2))
    done = 0
    batch: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for info in pool.map(lambda pr: extract(pr[0], pr[1], paths.thumbs, paths.playable), todo):
            done += 1
            if progress and (done % 50 == 0 or done == len(todo)):
                progress(done, len(todo))
            report.by_type[info["media_type"]] += 1
            report.by_status[info["status"]] += 1
            report.ts_sources[info.get("ts_source") or "none"] += 1
            if info["status"] != "ok":
                report.problems.append({"file": info["path"], "status": info["status"], "error": info["error"]})
            if info["path"] in existing:
                report.updated += 1
            else:
                report.new += 1
            batch.append(_row(info, run_id))
            if len(batch) >= 500:
                _upsert(conn, batch)
    _upsert(conn, batch)

    # Files that disappeared since the last scan of these roots: keep the row
    # (and the user's notes) but mark it missing.
    seen = {str(p.resolve()) for p, _ in files}
    for root in roots:
        prefix = str(root.resolve())
        for r in conn.execute("SELECT id, path FROM media WHERE path LIKE ? AND status != 'missing'",
                              (prefix.replace("%", "\\%") + "%",)).fetchall():
            if r["path"] not in seen and not Path(r["path"]).exists():
                conn.execute("UPDATE media SET status = 'missing', error = 'file not found' WHERE id = ?", (r["id"],))
                report.missing_marked += 1
    conn.commit()

    report.duplicates = mark_duplicates(conn)
    finish_run(conn, run_id, report.to_dict())
    return report


def _upsert(conn: sqlite3.Connection, batch: list[dict[str, Any]]) -> None:
    if not batch:
        return
    cols = ", ".join(_COLUMNS)
    placeholders = ", ".join(f":{c}" for c in _COLUMNS)
    # Refresh derived facts; keep user edits (title, note, hidden, manual date/association).
    updates = ", ".join(
        f"{c} = excluded.{c}" for c in _COLUMNS
        if c not in ("path", "ts", "day", "ts_source")
    )
    conn.executemany(
        f"""
        INSERT INTO media ({cols}) VALUES ({placeholders})
        ON CONFLICT(path) DO UPDATE SET {updates},
            ts = CASE WHEN media.ts_source = 'manual' THEN media.ts ELSE excluded.ts END,
            day = CASE WHEN media.ts_source = 'manual' THEN media.day ELSE excluded.day END,
            ts_source = CASE WHEN media.ts_source = 'manual' THEN media.ts_source ELSE excluded.ts_source END
        """,
        batch,
    )
    conn.commit()
    batch.clear()


def mark_duplicates(conn: sqlite3.Connection) -> int:
    conn.execute("UPDATE media SET duplicate_of = NULL")
    conn.execute(
        """
        UPDATE media SET duplicate_of = (SELECT MIN(m2.id) FROM media m2 WHERE m2.hash = media.hash AND m2.status = 'ok')
        WHERE hash IS NOT NULL AND status = 'ok'
          AND id > (SELECT MIN(m2.id) FROM media m2 WHERE m2.hash = media.hash AND m2.status = 'ok')
        """
    )
    conn.commit()
    return conn.execute("SELECT COUNT(*) FROM media WHERE duplicate_of IS NOT NULL").fetchone()[0]
