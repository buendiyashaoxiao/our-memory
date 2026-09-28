"""FFmpeg integration with graceful fallbacks.

Lookup order: ``MEMORY_MUSEUM_FFMPEG`` / ``MEMORY_MUSEUM_FFPROBE`` env vars,
then ``ffmpeg``/``ffprobe`` on PATH, then the static binary bundled with the
``imageio-ffmpeg`` pip package. If nothing is found the app still works:
images are fully supported via Pillow, WAV duration is read natively, and
other audio/video simply lack duration/thumbnails.
"""

from __future__ import annotations

import array
import json
import os
import re
import shutil
import subprocess
import sys
import wave
from functools import lru_cache
from pathlib import Path
from typing import Any

from memory_museum.timeutil import TimestampError, fmt, parse_timestamp

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
TIMEOUT = 120


@lru_cache(maxsize=1)
def find_ffmpeg() -> str | None:
    env = os.environ.get("MEMORY_MUSEUM_FFMPEG")
    if env and Path(env).exists():
        return env
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg

        exe = imageio_ffmpeg.get_ffmpeg_exe()
        return exe if exe and Path(exe).exists() else None
    except Exception:
        return None


@lru_cache(maxsize=1)
def find_ffprobe() -> str | None:
    env = os.environ.get("MEMORY_MUSEUM_FFPROBE")
    if env and Path(env).exists():
        return env
    found = shutil.which("ffprobe")
    if found:
        return found
    ff = find_ffmpeg()
    if ff:
        sibling = Path(ff).with_name("ffprobe" + (".exe" if sys.platform == "win32" else ""))
        if sibling.exists():
            return str(sibling)
    return None


def _run(args: list[str], *, capture_stdout: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        stdout=subprocess.PIPE if capture_stdout else subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        timeout=TIMEOUT,
        creationflags=_NO_WINDOW,
        check=False,
    )


def _parse_creation(value: str | None) -> str | None:
    if not value:
        return None
    try:
        dt = parse_timestamp(value.strip())
    except TimestampError:
        return None
    if dt.year < 2000:  # many devices write 1970/1904 placeholders
        return None
    return fmt(dt)


def _probe_ffprobe(path: Path, exe: str) -> dict[str, Any]:
    proc = _run([exe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)])
    if proc.returncode != 0:
        raise MediaProbeError(proc.stderr.decode("utf-8", "replace").strip()[:300] or "ffprobe failed")
    data = json.loads(proc.stdout or b"{}")
    fmt_ = data.get("format") or {}
    tags = {k.lower(): v for k, v in (fmt_.get("tags") or {}).items()}
    out: dict[str, Any] = {"duration": _float(fmt_.get("duration")), "format": fmt_.get("format_name")}
    for s in data.get("streams") or []:
        stags = {k.lower(): v for k, v in (s.get("tags") or {}).items()}
        if s.get("codec_type") == "video" and "width" not in out and s.get("disposition", {}).get("attached_pic") != 1:
            out.update(width=s.get("width"), height=s.get("height"), codec=s.get("codec_name"))
            rot = stags.get("rotate")
            for sd in s.get("side_data_list") or []:
                if "rotation" in sd:
                    rot = sd["rotation"]
            if rot is not None:
                out["rotation"] = int(float(rot))
            out["duration"] = out["duration"] or _float(s.get("duration"))
        elif s.get("codec_type") == "audio" and "audio_codec" not in out:
            out.update(audio_codec=s.get("codec_name"), sample_rate=_int(s.get("sample_rate")),
                       channels=s.get("channels"))
            out["duration"] = out["duration"] or _float(s.get("duration"))
        tags = {**stags, **tags}
    out["creation_time"] = _parse_creation(tags.get("com.apple.quicktime.creationdate") or tags.get("creation_time"))
    return out


_DURATION = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
_VIDEO = re.compile(r"Stream #\S+.*?: Video: (\w+)[^\n]*?,\s(\d{2,5})x(\d{2,5})")
_AUDIO = re.compile(r"Stream #\S+.*?: Audio: (\w+)[^\n]*?(\d+) Hz(?:,\s*([\w.]+))?")
_CREATION = re.compile(r"^\s*(com\.apple\.quicktime\.creationdate|creation_time)\s*:\s*(\S+)", re.MULTILINE)
_ROTATE = re.compile(r"(?:rotation of (-?\d+(?:\.\d+)?) degrees|^\s*rotate\s*:\s*(-?\d+))", re.MULTILINE)


def _probe_ffmpeg_stderr(path: Path, exe: str) -> dict[str, Any]:
    proc = _run([exe, "-hide_banner", "-i", str(path)])
    text = proc.stderr.decode("utf-8", "replace")
    if "Invalid data found" in text or "moov atom not found" in text or "No such file" in text:
        raise MediaProbeError(text.strip().splitlines()[-1][:300] if text.strip() else "ffmpeg could not read file")
    out: dict[str, Any] = {}
    m = _DURATION.search(text)
    if m:
        out["duration"] = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    m = _VIDEO.search(text)
    if m:
        out.update(codec=m.group(1), width=int(m.group(2)), height=int(m.group(3)))
    m = _AUDIO.search(text)
    if m:
        out.update(audio_codec=m.group(1), sample_rate=int(m.group(2)))
        if m.group(3):
            out["channels"] = {"mono": 1, "stereo": 2}.get(m.group(3), m.group(3))
    created = dict((k, v) for k, v in _CREATION.findall(text))
    out["creation_time"] = _parse_creation(created.get("com.apple.quicktime.creationdate") or created.get("creation_time"))
    m = _ROTATE.search(text)
    if m:
        out["rotation"] = int(float(m.group(1) or m.group(2)))
    if not out.get("duration") and not out.get("codec") and not out.get("audio_codec"):
        raise MediaProbeError("no audio or video stream found")
    return out


def _probe_wav(path: Path) -> dict[str, Any]:
    try:
        with wave.open(str(path), "rb") as w:
            frames, rate = w.getnframes(), w.getframerate()
            return {"duration": frames / float(rate) if rate else None, "audio_codec": "pcm",
                    "sample_rate": rate, "channels": w.getnchannels()}
    except (wave.Error, EOFError, OSError) as e:
        raise MediaProbeError(f"unreadable WAV: {e}") from e


class MediaProbeError(Exception):
    pass


def probe(path: Path) -> dict[str, Any]:
    """Return duration/resolution/codec/creation info. Raises MediaProbeError on corrupt files."""
    probe_exe = find_ffprobe()
    if probe_exe:
        try:
            return _probe_ffprobe(path, probe_exe)
        except (json.JSONDecodeError, subprocess.TimeoutExpired, OSError) as e:
            raise MediaProbeError(str(e)) from e
    ff = find_ffmpeg()
    if ff:
        try:
            return _probe_ffmpeg_stderr(path, ff)
        except (subprocess.TimeoutExpired, OSError) as e:
            raise MediaProbeError(str(e)) from e
    if path.suffix.lower() == ".wav":
        return _probe_wav(path)
    return {}


def video_thumbnail(path: Path, out: Path, duration: float | None, max_side: int = 640) -> bool:
    ff = find_ffmpeg()
    if not ff:
        return False
    out.parent.mkdir(parents=True, exist_ok=True)
    offsets = [min(1.0, (duration or 0) / 3), 0.0]
    for off in offsets:
        proc = _run([
            ff, "-v", "error", "-y", "-ss", f"{off:.2f}", "-i", str(path), "-frames:v", "1",
            "-vf", f"scale='if(gt(iw,ih),min({max_side},iw),-2)':'if(gt(iw,ih),-2,min({max_side},ih))'",
            "-q:v", "4", str(out),
        ], capture_stdout=False)
        if proc.returncode == 0 and out.exists() and out.stat().st_size > 0:
            return True
    return False


def _peaks(samples: array.array, buckets: int) -> list[float]:
    n = len(samples)
    if n == 0:
        return []
    size = max(1, n // buckets)
    peaks = []
    for i in range(0, n, size):
        chunk = samples[i:i + size]
        peaks.append(max(abs(min(chunk)), abs(max(chunk))))
    peaks = peaks[:buckets]
    top = max(peaks) or 1
    return [round(p / top, 3) for p in peaks]


def waveform(path: Path, buckets: int = 48) -> list[float] | None:
    """Real amplitude peaks (0..1) for an audio file, or None if it cannot be decoded."""
    ff = find_ffmpeg()
    samples = array.array("h")
    if ff:
        try:
            proc = _run([ff, "-v", "error", "-i", str(path), "-ac", "1", "-ar", "2000", "-f", "s16le", "-"])
        except (subprocess.TimeoutExpired, OSError):
            return None
        if proc.returncode != 0 or not proc.stdout:
            return None
        raw = proc.stdout[: len(proc.stdout) - len(proc.stdout) % 2]
        samples.frombytes(raw)
    elif path.suffix.lower() == ".wav":
        try:
            with wave.open(str(path), "rb") as w:
                if w.getsampwidth() != 2:
                    return None
                channels = w.getnchannels()
                samples.frombytes(w.readframes(w.getnframes()))
                if channels > 1:
                    samples = samples[::channels]
        except (wave.Error, EOFError, OSError):
            return None
    else:
        return None
    if sys.byteorder == "big":
        samples.byteswap()
    return _peaks(samples, buckets) or None


BROWSER_UNFRIENDLY_AUDIO = {".amr", ".wma", ".silk", ".caf", ".3ga"}


def transcode_audio(path: Path, out: Path) -> bool:
    ff = find_ffmpeg()
    if not ff:
        return False
    out.parent.mkdir(parents=True, exist_ok=True)
    proc = _run([ff, "-v", "error", "-y", "-i", str(path), "-vn", "-c:a", "aac", "-b:a", "64k", str(out)],
                capture_stdout=False)
    return proc.returncode == 0 and out.exists() and out.stat().st_size > 0


def _float(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _int(v) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def capabilities() -> dict[str, Any]:
    return {"ffmpeg": find_ffmpeg(), "ffprobe": find_ffprobe()}
