"""Per-file media metadata extraction (runs in worker threads, no DB access)."""

from __future__ import annotations

import hashlib
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError

from memory_museum.media import ffmpeg
from memory_museum.parsers.base import AUDIO_EXTS, IMAGE_EXTS, VIDEO_EXTS
from memory_museum.timeutil import TimestampError, fmt, parse_timestamp, timestamp_from_filename

Image.MAX_IMAGE_PIXELS = 200_000_000  # large panoramas are fine; still guards against decompression bombs

THUMB_MAX = 640
VOICE_HINTS = ("voice", "语音", "ptt", "voice_note", "voicenote", "录音")
VOICE_EXTS = {".amr", ".silk", ".opus"}

# EXIF tags
_DATETIME_ORIGINAL = 36867
_DATETIME_DIGITIZED = 36868
_DATETIME = 306
_ORIENTATION = 274
_EXIF_IFD = 0x8769


def classify(path: Path) -> str | None:
    ext = path.suffix.lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in VIDEO_EXTS:
        return "video"
    if ext in AUDIO_EXTS:
        lowered = str(path).lower()
        if ext in VOICE_EXTS or any(h in lowered for h in VOICE_HINTS) or path.name.upper().startswith("PTT-"):
            return "voice"
        return "audio"
    return None


def quick_hash(path: Path, chunk: int = 1 << 20) -> str:
    """Content fingerprint: full SHA-256 for small files, size+head+tail for large ones."""
    size = path.stat().st_size
    h = hashlib.sha256()
    h.update(str(size).encode())
    with path.open("rb") as fh:
        if size <= 2 * chunk:
            h.update(fh.read())
        else:
            h.update(fh.read(chunk))
            fh.seek(-chunk, os.SEEK_END)
            h.update(fh.read(chunk))
    return h.hexdigest()[:32]


def _exif_datetime(img: Image.Image) -> str | None:
    try:
        exif = img.getexif()
    except Exception:
        return None
    candidates = []
    try:
        sub = exif.get_ifd(_EXIF_IFD)
        candidates += [sub.get(_DATETIME_ORIGINAL), sub.get(_DATETIME_DIGITIZED)]
    except Exception:
        pass
    candidates.append(exif.get(_DATETIME))
    for raw in candidates:
        if not raw or not isinstance(raw, str):
            continue
        s = raw.strip().replace("\x00", "")
        if len(s) >= 19 and s[4] == ":" and s[7] == ":":
            s = s[:4] + "-" + s[5:7] + "-" + s[8:]
        try:
            dt = parse_timestamp(s[:19])
        except TimestampError:
            continue
        if dt.year >= 1990:
            return fmt(dt)
    return None


def _thumb_path(thumbs_dir: Path, digest: str) -> Path:
    return thumbs_dir / digest[:2] / f"{digest}.jpg"


def extract_image(path: Path, info: dict[str, Any], thumbs_dir: Path) -> None:
    try:
        with Image.open(path) as probe:
            probe.verify()
        with Image.open(path) as img:
            info["codec"] = (img.format or "").lower() or None
            info["orientation"] = img.getexif().get(_ORIENTATION) if hasattr(img, "getexif") else None
            exif_ts = _exif_datetime(img)
            if exif_ts:
                info["ts"], info["ts_source"] = exif_ts, "exif"
            img.seek(0)
            img.load()
            upright = ImageOps.exif_transpose(img) or img
            info["width"], info["height"] = upright.size
            if getattr(img, "is_animated", False):
                info["metadata"]["animated"] = True
            thumb = _thumb_path(thumbs_dir, info["hash"])
            if not thumb.exists():
                thumb.parent.mkdir(parents=True, exist_ok=True)
                t = upright.convert("RGBA") if upright.mode in ("P", "LA", "RGBA") else upright
                if t.mode == "RGBA":
                    bg = Image.new("RGB", t.size, (246, 243, 238))
                    bg.paste(t, mask=t.split()[-1])
                    t = bg
                elif t.mode != "RGB":
                    t = t.convert("RGB")
                t.thumbnail((THUMB_MAX, THUMB_MAX), Image.Resampling.LANCZOS)
                t.save(thumb, "JPEG", quality=80, optimize=True, progressive=True)
            info["thumb_path"] = str(thumb)
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError) as e:
        if path.suffix.lower() in (".heic", ".heif"):
            info["status"], info["error"] = "unsupported", "HEIC is not supported yet (convert to JPEG first)"
        else:
            info["status"], info["error"] = "corrupt", f"unreadable image: {e}"[:300]


def extract_av(path: Path, info: dict[str, Any], thumbs_dir: Path, playable_dir: Path, *, waveforms: bool = True) -> None:
    try:
        meta = ffmpeg.probe(path)
    except ffmpeg.MediaProbeError as e:
        info["status"], info["error"] = "corrupt", str(e)[:300]
        return
    info["duration"] = meta.get("duration")
    info["width"], info["height"] = meta.get("width"), meta.get("height")
    if meta.get("rotation") in (90, -90, 270, -270) and info["width"] and info["height"]:
        info["width"], info["height"] = info["height"], info["width"]
    info["codec"] = meta.get("codec") or meta.get("audio_codec")
    for k in ("audio_codec", "sample_rate", "channels", "format"):
        if meta.get(k) is not None:
            info["metadata"][k] = meta[k]
    if meta.get("creation_time"):
        info["ts"], info["ts_source"] = meta["creation_time"], "media_meta"

    if info["media_type"] == "video":
        thumb = _thumb_path(thumbs_dir, info["hash"])
        if thumb.exists() or ffmpeg.video_thumbnail(path, thumb, info["duration"]):
            info["thumb_path"] = str(thumb)
        if not meta and not ffmpeg.find_ffmpeg():
            info["metadata"]["note"] = "ffmpeg not found: no duration/thumbnail"
    else:
        if waveforms:
            peaks = ffmpeg.waveform(path)
            if peaks:
                info["waveform"] = peaks
        if path.suffix.lower() in ffmpeg.BROWSER_UNFRIENDLY_AUDIO:
            out = playable_dir / f"{info['hash']}.m4a"
            if out.exists() or ffmpeg.transcode_audio(path, out):
                info["playable_path"] = str(out)
            else:
                info["metadata"]["playback"] = "format may not play in browsers; install ffmpeg to convert"


def extract(path: Path, root: Path, thumbs_dir: Path, playable_dir: Path) -> dict[str, Any]:
    """Collect everything we can learn about one file. Never raises."""
    media_type = classify(path) or "file"
    info: dict[str, Any] = {
        "path": str(path.resolve()),
        "rel_path": str(path.relative_to(root)) if path.is_relative_to(root) else path.name,
        "media_type": media_type,
        "original_filename": path.name,
        "ext": path.suffix.lower(),
        "status": "ok",
        "error": None,
        "ts": None,
        "ts_source": None,
        "duration": None,
        "width": None,
        "height": None,
        "orientation": None,
        "codec": None,
        "thumb_path": None,
        "playable_path": None,
        "waveform": None,
        "metadata": {},
    }
    try:
        st = path.stat()
        info["size_bytes"], info["mtime"] = st.st_size, st.st_mtime
        info["hash"] = quick_hash(path)
    except OSError as e:
        info.update(status="missing", error=str(e)[:300], size_bytes=None, mtime=None, hash=None)
        return info
    if info["size_bytes"] == 0:
        info.update(status="corrupt", error="empty file")
        return info

    try:
        if media_type == "image":
            extract_image(path, info, thumbs_dir)
        elif media_type in ("video", "audio", "voice"):
            extract_av(path, info, thumbs_dir, playable_dir)
    except Exception as e:  # one broken file must never stop the import
        info["status"], info["error"] = "corrupt", f"{type(e).__name__}: {e}"[:300]

    if not info["ts"]:
        from_name = timestamp_from_filename(path.name)
        if from_name:
            dt, precise = from_name
            info["ts"], info["ts_source"] = fmt(dt), "filename" if precise else "filename_date"
    if not info["ts"] and info.get("mtime"):
        info["ts"], info["ts_source"] = fmt(datetime.fromtimestamp(info["mtime"])), "mtime"
    return info
