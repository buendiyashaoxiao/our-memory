"""Synthetic data generator.

``generate_demo`` writes the small, committed demo dataset (fictional couple,
~7 months, all media procedurally generated). ``generate_stress`` writes a
large dataset for performance testing into an ignored folder.

Nothing here uses real personal data.
"""

from __future__ import annotations

import csv
import json
import math
import os
import random
import shutil
import struct
import subprocess
import wave
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter

from memory_museum import demo_content as C
from memory_museum.media.ffmpeg import find_ffmpeg

NAMES = {C.A: "林夏", C.B: "周屿"}
START = date(2025, 3, 1)
END = date(2025, 9, 30)


# ------------------------------------------------------------------ images

def _gradient(w: int, h: int, stops: list[tuple[float, tuple[int, int, int]]]) -> Image.Image:
    col = Image.new("RGB", (1, 256))
    for y in range(256):
        p = y / 255
        for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
            if p0 <= p <= p1:
                t = 0 if p1 == p0 else (p - p0) / (p1 - p0)
                col.putpixel((0, y), tuple(int(c0[i] + (c1[i] - c0[i]) * t) for i in range(3)))
                break
        else:
            col.putpixel((0, y), stops[-1][1] if p > stops[-1][0] else stops[0][1])
    return col.resize((w, h), Image.Resampling.BILINEAR)


def _layer(size) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    return layer, ImageDraw.Draw(layer)


def _paste(img: Image.Image, layer: Image.Image, blur: float) -> Image.Image:
    if blur:  # blur premultiplied, otherwise transparent black bleeds into edges as a dark fringe
        layer = layer.convert("RGBa").filter(ImageFilter.GaussianBlur(blur)).convert("RGBA")
    base = img.convert("RGBA")
    base.alpha_composite(layer)
    return base.convert("RGB")


def _bokeh(img, rng, n, colors, rmin, rmax, blur, amin=70, amax=170, area=(0, 0, 1, 1)):
    w, h = img.size
    layer, d = _layer(img.size)
    for _ in range(n):
        r = rng.uniform(rmin, rmax) * w / 1000
        x = rng.uniform(area[0], area[2]) * w
        y = rng.uniform(area[1], area[3]) * h
        c = rng.choice(colors)
        d.ellipse([x - r, y - r, x + r, y + r], fill=(*c, rng.randint(amin, amax)))
    return _paste(img, layer, blur * w / 1000)


def _glow(img, cx, cy, r, color, alpha, blur):
    w, _ = img.size
    layer, d = _layer(img.size)
    rr = r * w
    d.ellipse([cx * w - rr, cy * img.size[1] - rr, cx * w + rr, cy * img.size[1] + rr], fill=(*color, alpha))
    return _paste(img, layer, blur * w / 1000)


def _finish(img: Image.Image, rng: random.Random, vignette: float = 0.45, grain: float = 0.05) -> Image.Image:
    w, h = img.size
    mask = Image.radial_gradient("L").resize((w, h)).point(lambda v: int(min(255, max(0, (v - 90) * 1.6)) * vignette))
    img = Image.composite(Image.new("RGB", (w, h), (14, 10, 16)), img, mask)
    noise = Image.effect_noise((w, h), 40).convert("RGB")
    img = Image.blend(img, noise, grain)
    # gentle film tone: lift blacks a little, warm highlights
    return img.point(lambda v: int(12 + v * 0.93))


def render_scene(scene: str, w: int, h: int, rng: random.Random) -> Image.Image:
    if scene in ("sunset", "sunrise"):
        horizon = rng.uniform(0.58, 0.66)
        sky = ([(0, (52, 58, 104)), (horizon - 0.18, (224, 148, 128)), (horizon, (252, 208, 162))] if scene == "sunset"
               else [(0, (44, 58, 98)), (horizon - 0.2, (206, 164, 178)), (horizon, (255, 220, 176))])
        img = _gradient(w, h, sky + [(horizon + 0.001, (86, 90, 122)), (1, (28, 32, 56))])
        sx = rng.uniform(0.35, 0.65)
        img = _glow(img, sx, horizon - 0.03, 0.22, (255, 200, 150), 110, 90)
        img = _glow(img, sx, horizon - 0.035, 0.045, (255, 236, 205), 255, 6)
        layer, d = _layer(img.size)
        for i in range(40):
            y = (horizon + 0.01 + i * 0.008 + rng.uniform(0, 0.004)) * h
            half = rng.uniform(0.02, 0.12) * w * (1 - i / 50)
            d.line([(sx * w - half, y), (sx * w + half, y)], fill=(255, 214, 170, rng.randint(60, 150)), width=2)
        img = _paste(img, layer, 2)
    elif scene == "sea":
        horizon = rng.uniform(0.42, 0.52)
        img = _gradient(w, h, [(0, (146, 186, 214)), (horizon, (222, 232, 234)), (horizon + 0.001, (84, 132, 158)),
                               (0.82, (40, 84, 110)), (0.83, (214, 200, 176)), (1, (190, 172, 148))])
        layer, d = _layer(img.size)
        for i in range(60):
            y = rng.uniform(horizon + 0.02, 0.83) * h
            x = rng.uniform(0, 1) * w
            L = rng.uniform(0.05, 0.3) * w
            d.line([(x, y), (x + L, y)], fill=(240, 246, 248, rng.randint(40, 130)), width=rng.randint(1, 3))
        d.rectangle([0, 0.81 * h, w, 0.835 * h], fill=(250, 250, 248, 170))
        img = _paste(img, layer, 1.5)
        img = _glow(img, 0.8, 0.12, 0.3, (255, 250, 235), 90, 120)
    elif scene == "night_city":
        img = _gradient(w, h, [(0, (10, 12, 28)), (0.6, (28, 24, 44)), (1, (46, 30, 40))])
        warm = [(255, 190, 110), (255, 160, 90), (250, 228, 170), (255, 130, 120), (150, 185, 255)]
        img = _bokeh(img, rng, 45, warm, 14, 60, 9, 40, 120, area=(0, 0.25, 1, 0.95))
        img = _bokeh(img, rng, 30, warm, 3, 8, 1.5, 150, 230, area=(0, 0.3, 1, 0.9))
    elif scene == "cafe":
        img = _gradient(w, h, [(0, (74, 50, 38)), (0.55, (132, 96, 72)), (0.56, (176, 136, 104)), (1, (120, 86, 62))])
        img = _glow(img, 0.2, 0.18, 0.3, (255, 236, 205), 160, 70)
        layer, d = _layer(img.size)
        cx, cy, cw = rng.uniform(0.4, 0.6) * w, 0.7 * h, 0.2 * w
        d.ellipse([cx - cw, cy - cw * 0.45, cx + cw, cy + cw * 0.45], fill=(238, 230, 218, 255))
        d.ellipse([cx - cw * 0.78, cy - cw * 0.33, cx + cw * 0.78, cy + cw * 0.33], fill=(104, 64, 40, 255))
        d.ellipse([cx - cw * 0.35, cy - cw * 0.12, cx + cw * 0.2, cy + cw * 0.1], fill=(196, 150, 110, 200))
        img = _paste(img, layer, 3)
        img = _bokeh(img, rng, 14, [(255, 214, 160), (255, 240, 210)], 20, 60, 14, 40, 90, area=(0, 0, 1, 0.45))
    elif scene == "park":
        img = _gradient(w, h, [(0, (214, 222, 186)), (0.45, (128, 164, 104)), (1, (46, 74, 44))])
        img = _bokeh(img, rng, 60, [(236, 240, 170), (196, 222, 140), (255, 250, 210), (120, 170, 90)], 15, 60, 10)
        img = _glow(img, 0.85, 0.05, 0.35, (255, 196, 120), 120, 110)
    elif scene == "rain":
        img = _gradient(w, h, [(0, (74, 88, 110)), (1, (34, 42, 58))])
        img = _bokeh(img, rng, 30, [(255, 190, 120), (250, 120, 100), (150, 200, 255)], 30, 90, 22, 60, 140,
                     area=(0, 0.35, 1, 1))
        layer, d = _layer(img.size)
        for _ in range(160):
            x, y, r = rng.uniform(0, w), rng.uniform(0, h), rng.uniform(2, 9) * w / 1000
            d.ellipse([x - r, y - r * 1.2, x + r, y + r * 1.2], fill=(210, 225, 240, rng.randint(60, 150)))
        for _ in range(25):
            x, y = rng.uniform(0, w), rng.uniform(0, h * 0.7)
            d.line([(x, y), (x + rng.uniform(-4, 4), y + rng.uniform(40, 160))], fill=(200, 215, 235, 60), width=2)
        img = _paste(img, layer, 1)
    elif scene == "flowers":
        img = _gradient(w, h, [(0, (246, 234, 228)), (1, (226, 196, 196))])
        layer, d = _layer(img.size)
        for _ in range(12):
            cx, cy = rng.uniform(0.1, 0.9) * w, rng.uniform(0.2, 0.9) * h
            for k in range(6):
                a = k * math.pi / 3 + rng.uniform(0, 0.4)
                r = rng.uniform(0.04, 0.08) * w
                px, py = cx + math.cos(a) * r, cy + math.sin(a) * r
                col = rng.choice([(236, 150, 164), (248, 206, 214), (252, 244, 240), (226, 120, 140)])
                d.ellipse([px - r * 0.8, py - r * 0.8, px + r * 0.8, py + r * 0.8], fill=(*col, 190))
            d.ellipse([cx - 10, cy - 10, cx + 10, cy + 10], fill=(240, 200, 110, 230))
        img = _paste(img, layer, 9)
    elif scene == "window":
        img = _gradient(w, h, [(0, (224, 218, 206)), (1, (176, 164, 150))])
        layer, d = _layer(img.size)
        x0, y0, x1, y1 = 0.22 * w, 0.12 * h, 0.8 * w, 0.62 * h
        d.rectangle([x0, y0, x1, y1], fill=(208, 228, 242, 255))
        d.rectangle([x0, (y0 + y1) / 2 - 4, x1, (y0 + y1) / 2 + 4], fill=(244, 240, 232, 255))
        d.rectangle([(x0 + x1) / 2 - 4, y0, (x0 + x1) / 2 + 4, y1], fill=(244, 240, 232, 255))
        d.rectangle([0, 0, 0.18 * w, h], fill=(232, 218, 196, 200))
        d.polygon([(x0, 0.75 * h), (x1, 0.75 * h), (x1 + 0.1 * w, h), (x0 - 0.05 * w, h)], fill=(255, 244, 222, 110))
        img = _paste(img, layer, 5)
    elif scene == "snow":
        img = _gradient(w, h, [(0, (196, 206, 218)), (1, (236, 238, 242))])
        layer, d = _layer(img.size)
        for _ in range(18):
            x = rng.uniform(0, w)
            d.line([(x, rng.uniform(0.2, 0.5) * h), (x, 0.85 * h)], fill=(70, 72, 80, 180), width=rng.randint(3, 9))
        img = _paste(img, layer, 6)
        img = _bokeh(img, rng, 200, [(255, 255, 255)], 2, 7, 1, 150, 230)
    elif scene == "candles":
        img = _gradient(w, h, [(0, (18, 12, 12)), (1, (48, 30, 22))])
        img = _glow(img, 0.5, 0.55, 0.4, (255, 150, 70), 90, 140)
        layer, d = _layer(img.size)
        d.ellipse([0.2 * w, 0.62 * h, 0.8 * w, 0.8 * h], fill=(236, 220, 206, 170))
        img = _paste(img, layer, 6)
        for i in range(5):
            x = 0.32 + i * 0.09
            img = _glow(img, x, 0.55, 0.012, (255, 226, 160), 255, 3)
            img = _glow(img, x, 0.55, 0.04, (255, 180, 90), 120, 18)
    else:
        img = _gradient(w, h, [(0, (200, 200, 205)), (1, (120, 120, 130))])
    return _finish(img, rng)


def _exif_bytes(dt: datetime | None, orientation: int = 1) -> Image.Exif:
    exif = Image.Exif()
    exif[271] = "DemoCam"  # Make (fictional)
    exif[272] = "Synthetic 1"
    exif[274] = orientation
    if dt:
        s = dt.strftime("%Y:%m:%d %H:%M:%S")
        exif[306] = s
        ifd = exif.get_ifd(0x8769)
        ifd[36867] = s
        ifd[36868] = s
    return exif


def save_photo(path: Path, scene: str, rng: random.Random, taken: datetime | None, *, portrait: bool | None = None,
               orientation: int = 1, size: int = 960) -> None:
    portrait = rng.random() < 0.55 if portrait is None else portrait
    w, h = (size * 3 // 4, size) if portrait else (size, size * 3 // 4)
    img = render_scene(scene, w, h, rng)
    if orientation == 6:  # stored sideways, EXIF says rotate 90° CW to view
        img = img.transpose(Image.Transpose.ROTATE_90)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "JPEG", quality=80, optimize=True, progressive=True, exif=_exif_bytes(taken, orientation))


# ------------------------------------------------------------------ audio

def synth_voice(seconds: float, base_hz: float, rng: random.Random, rate: int = 16000) -> bytes:
    """Speech-like placeholder: syllables with a pitch contour and soft harmonics (not real speech)."""
    n = int(seconds * rate)
    out = bytearray()
    phase = 0.0
    syll_len = int(rate * rng.uniform(0.16, 0.24))
    t_in_syll, syll_pitch, gap = 0, base_hz, 0
    phrase_pos = 0
    for i in range(n):
        if gap > 0:
            gap -= 1
            sample = rng.gauss(0, 60)
        else:
            if t_in_syll >= syll_len:
                t_in_syll = 0
                phrase_pos += 1
                syll_len = int(rate * rng.uniform(0.12, 0.26))
                syll_pitch = base_hz * (1 + 0.18 * math.sin(phrase_pos * 0.9) + rng.uniform(-0.08, 0.08))
                if rng.random() < 0.18:
                    gap = int(rate * rng.uniform(0.15, 0.45))
            env = math.sin(math.pi * t_in_syll / syll_len) ** 1.5
            phase += 2 * math.pi * syll_pitch * (1 + 0.02 * math.sin(i / 400)) / rate
            s = math.sin(phase) + 0.45 * math.sin(2 * phase) + 0.22 * math.sin(3 * phase) + 0.1 * math.sin(5 * phase)
            sample = s * env * 5200 + rng.gauss(0, 90)
            t_in_syll += 1
        fade = min(1.0, i / (rate * 0.05), (n - i) / (rate * 0.08))
        out += struct.pack("<h", int(max(-32767, min(32767, sample * fade))))
    return bytes(out)


def write_wav(path: Path, pcm: bytes, rate: int = 16000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)


def encode_audio(pcm: bytes, out: Path, rate: int = 16000) -> Path:
    """Encode to the extension of ``out`` with ffmpeg; falls back to WAV."""
    ff = find_ffmpeg()
    out.parent.mkdir(parents=True, exist_ok=True)
    if not ff or out.suffix == ".wav":
        target = out.with_suffix(".wav")
        write_wav(target, pcm, rate)
        return target
    codec = {".m4a": ["-c:a", "aac", "-b:a", "32k"], ".mp3": ["-c:a", "libmp3lame", "-b:a", "48k"],
             ".amr": ["-c:a", "libopencore_amrnb", "-ar", "8000", "-b:a", "12.2k"]}[out.suffix]
    proc = subprocess.run([ff, "-v", "error", "-y", "-f", "s16le", "-ar", str(rate), "-ac", "1", "-i", "-", *codec,
                           str(out)], input=pcm, capture_output=True, check=False)
    if proc.returncode != 0:
        target = out.with_suffix(".wav")
        write_wav(target, pcm, rate)
        return target
    return out


# ------------------------------------------------------------------ video

def save_video(path: Path, scene: str, seconds: float, rng: random.Random) -> bool:
    """Slow Ken Burns pan across a generated scene, encoded as H.264 MP4."""
    ff = find_ffmpeg()
    if not ff:
        return False
    w, h, fps = 360, 640, 24
    big = render_scene(scene, 540, 960, rng)
    frames = int(seconds * fps)
    path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen([ff, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r",
                             str(fps), "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "30", "-preset",
                             "veryfast", "-movflags", "+faststart", str(path)],
                            stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for f in range(frames):
            t = f / max(1, frames - 1)
            scale = 1.0 - 0.18 * t
            cw, ch = int(540 * scale), int(960 * scale)
            x0, y0 = int((540 - cw) * (0.2 + 0.6 * t)), int((960 - ch) * 0.5)
            frame = big.crop((x0, y0, x0 + cw, y0 + ch)).resize((w, h), Image.Resampling.BILINEAR)
            if scene == "candles":
                frame = frame.point(lambda v, k=1 + 0.06 * math.sin(f * 1.7): int(min(255, v * k)))
            proc.stdin.write(frame.tobytes())
        proc.stdin.close()
        proc.wait(timeout=120)
    except (BrokenPipeError, subprocess.TimeoutExpired):
        proc.kill()
        return False
    return proc.returncode == 0


# ------------------------------------------------------------------ chat plan

@dataclass
class Event:
    ts: datetime
    sender: str
    kind: str  # text | image | video | voice | sticker | link | system
    text: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    media_ref: str | None = None


def _other(s: str) -> str:
    return C.B if s == C.A else C.A


def _snippet_events(start: datetime, snippet, initiator: str, rng: random.Random) -> list[Event]:
    t = start
    out = []
    for speaker, text in snippet:
        sender = initiator if speaker == 0 else _other(initiator)
        out.append(Event(t, sender, "text", text))
        t += timedelta(seconds=rng.randint(8, 180))
    return out


def _at(day: date, hh: int, mm: int, ss: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hh, mm, ss)


def build_plan(rng: random.Random, start: date = START, end: date = END) -> list[Event]:
    events: list[Event] = []
    day = start
    while day <= end:
        key = day.isoformat()
        if key in C.SPECIAL_DAYS:
            for hhmm, sender, kind, payload in C.SPECIAL_DAYS[key]:
                hh, mm = map(int, hhmm.split(":"))
                ts = _at(day, hh, mm, rng.randint(0, 50))
                if kind == "text":
                    events.append(Event(ts, sender, "text", payload))
                else:
                    ev = Event(ts, sender, kind, payload.get("caption") if isinstance(payload, dict) else None,
                               dict(payload) if isinstance(payload, dict) else {})
                    events.append(ev)
            day += timedelta(days=1)
            continue

        weekend = day.weekday() >= 5
        roll = rng.random()
        if roll < 0.06:
            level = 0
        elif roll < 0.3:
            level = 1
        elif roll < (0.8 if not weekend else 0.65):
            level = 2
        else:
            level = 3
        if level == 0:
            day += timedelta(days=1)
            continue
        blocks: list[tuple[int, int, list]] = []
        if level == 1:
            blocks = [(22, 30, C.NIGHT)] if rng.random() < 0.6 else [(8, 0, C.MORNING)]
        else:
            blocks = [(7 + rng.randint(0, 1), rng.randint(0, 50), C.MORNING), (12, rng.randint(0, 40), C.NOON),
                      (19, rng.randint(0, 50), C.EVENING), (22, rng.randint(10, 55), C.NIGHT)]
            if level == 3 or rng.random() < 0.5:
                blocks.insert(2, (15, rng.randint(0, 50), C.AFTERNOON))
            if level == 3:
                blocks += [(20, rng.randint(0, 50), C.SMALLTALK), (21, rng.randint(0, 50), C.SMALLTALK),
                           (23, rng.randint(0, 30), C.NIGHT)]
            elif rng.random() < 0.6:
                blocks.append((20, rng.randint(0, 59), C.SMALLTALK))
        for hh, mm, pool in blocks:
            base = _at(day, min(hh, 23), mm, rng.randint(0, 59))
            snippet = rng.choice(pool)
            initiator = rng.choice([C.A, C.B])
            evs = _snippet_events(base, snippet, initiator, rng)
            events += evs
            last = evs[-1].ts
            r = rng.random()
            if r < 0.07:
                events.append(Event(last + timedelta(seconds=20), rng.choice([C.A, C.B]), "sticker"))
            elif r < 0.12:
                events.append(Event(last + timedelta(seconds=15), _other(evs[-1].sender), "text", rng.choice(C.LAUGHS)))
            elif r < 0.14:
                url, title = rng.choice(C.LINKS)
                events.append(Event(last + timedelta(seconds=30), initiator, "link", f"{title} {url}"))
            elif r < 0.155:
                events.append(Event(last + timedelta(seconds=5), initiator, "system", "对方撤回了一条消息"))
            if level >= 2 and rng.random() < 0.13:
                who = rng.choice([C.A, C.B])
                t = last + timedelta(seconds=rng.randint(30, 200))
                events.append(Event(t, who, "text", rng.choice(C.PHOTO_CAPTIONS)))
                events.append(Event(t + timedelta(seconds=4), who, "image", payload={"scene": rng.choice(C.SCENES)}))
            if level >= 2 and rng.random() < 0.05:
                who = rng.choice([C.A, C.B])
                t = last + timedelta(seconds=rng.randint(30, 200))
                events.append(Event(t, who, "text", rng.choice(C.VOICE_LEADS)))
                events.append(Event(t + timedelta(seconds=10), who, "voice",
                                    payload={"seconds": rng.choice([4, 6, 8, 11, 15])}))
        day += timedelta(days=1)
    events.sort(key=lambda e: e.ts)
    return events


# ------------------------------------------------------------------ writers

def _materialize_media(events: list[Event], media_dir: Path, rng: random.Random) -> dict[str, int]:
    """Create media files for media events and set how each message references them."""
    counts = {"photos": 0, "voices": 0, "videos": 0}
    photo_i = 0
    for ev in events:
        stamp = ev.ts.strftime("%Y%m%d_%H%M%S")
        if ev.kind == "image":
            photo_i += 1
            taken = ev.ts - timedelta(seconds=rng.randint(15, 240))
            mode = photo_i % 20
            scene = ev.payload.get("scene", "window")
            if mode == 7:  # sent in chat under an opaque name, no EXIF -> exact match by filename
                name = f"{rng.getrandbits(40):010x}.jpg"
                save_photo(media_dir / "chat-images" / name, scene, rng, None)
                ev.media_ref = name
            elif mode in (3, 13):  # "[图片]" without filename -> fuzzy time match with the camera photo
                taken = ev.ts - timedelta(seconds=rng.randint(10, 80))
                save_photo(media_dir / "camera" / f"IMG_{taken.strftime('%Y%m%d_%H%M%S')}.jpg", scene, rng, taken)
                ev.media_ref = None
            elif mode == 17:  # referenced but the file was lost
                ev.media_ref = f"IMG_{taken.strftime('%Y%m%d_%H%M%S')}.jpg"
                continue
            else:
                name = f"IMG_{taken.strftime('%Y%m%d_%H%M%S')}.jpg"
                save_photo(media_dir / "camera" / name, scene, rng, taken, orientation=6 if mode == 11 else 1)
                ev.media_ref = name
            counts["photos"] += 1
        elif ev.kind == "voice":
            secs = float(ev.payload.get("seconds", 6))
            ev.payload["seconds"] = secs
            base = 225 if ev.sender == C.A else 128
            ext = ".m4a" if counts["voices"] % 5 else ".mp3"
            if counts["voices"] == 3:
                ext = ".amr"  # like many messenger exports; transcoded for browsers at import
            path = encode_audio(synth_voice(secs, base, rng), media_dir / "voice" / f"voice_{stamp}{ext}")
            ev.media_ref = path.name
            counts["voices"] += 1
        elif ev.kind == "video":
            name = f"VID_{stamp}.mp4"
            if save_video(media_dir / "camera" / name, ev.payload.get("scene", "sea"), ev.payload.get("seconds", 4), rng):
                ev.media_ref = name
                counts["videos"] += 1
            else:
                ev.media_ref = name
    return counts


def _json_record(i: int, ev: Event) -> dict[str, Any]:
    rec: dict[str, Any] = {"id": f"m{i:06d}", "time": ev.ts.strftime("%Y-%m-%d %H:%M:%S"), "sender_id": ev.sender,
                           "type": ev.kind}
    if ev.text:
        rec["text"] = ev.text
    if ev.media_ref:
        rec["media"] = ev.media_ref
    if ev.kind == "voice":
        rec["duration"] = ev.payload.get("seconds")
    return rec


def _txt_line(ev: Event) -> str:
    name = NAMES[ev.sender]
    t = ev.ts.strftime("%H:%M")
    if ev.kind == "image":
        body = f"[图片] {ev.media_ref}" if ev.media_ref else "[图片]"
    elif ev.kind == "voice":
        body = f"[语音] {ev.media_ref} {int(ev.payload.get('seconds', 0))}\""
    elif ev.kind == "video":
        body = f"[视频] {ev.media_ref}"
    elif ev.kind == "sticker":
        body = "[表情]"
    else:
        body = ev.text or ""
    return f"{t} {name}: {body}"


def generate_demo(out: Path, seed: int = 20250301) -> None:
    rng = random.Random(seed)
    chat_dir, media_dir = out / "chat", out / "media"
    for d in (chat_dir, media_dir):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)

    events = build_plan(rng)
    _materialize_media(events, media_dir, rng)

    # Camera-roll photos never sent in chat (they still appear in the gallery by capture time)
    for day_s, hh, scene in [("2025-03-22", 16, "park"), ("2025-04-19", 18, "sunset"), ("2025-05-01", 19, "night_city"),
                             ("2025-06-01", 10, "window"), ("2025-06-21", 20, "rain"), ("2025-07-26", 15, "flowers"),
                             ("2025-08-16", 17, "sea"), ("2025-09-13", 11, "cafe")]:
        taken = datetime.fromisoformat(f"{day_s}T{hh:02d}:{rng.randint(0, 59):02d}:{rng.randint(0, 59):02d}")
        save_photo(media_dir / "camera" / f"IMG_{taken.strftime('%Y%m%d_%H%M%S')}.jpg", scene, rng, taken)
    # A messenger-style name that only carries a date (weak timestamp)
    save_photo(media_dir / "chat-images" / "IMG-20250614-WA0003.jpg", "flowers", rng, None)
    # An unreferenced voice memo
    encode_audio(synth_voice(18, 210, rng), media_dir / "voice" / "录音_20250720_231000.m4a")
    # Duplicates: the same photo backed up twice
    firsts = sorted((media_dir / "camera").glob("IMG_*.jpg"))
    (media_dir / "backup").mkdir(exist_ok=True)
    for p in firsts[:2]:
        shutil.copy2(p, media_dir / "backup" / p.name)
    # Corrupted and unsupported files
    broken = media_dir / "broken"
    broken.mkdir(exist_ok=True)
    (broken / "IMG_20250702_101010.jpg").write_bytes(b"\xff\xd8\xff\xe0" + bytes(rng.getrandbits(8) for _ in range(900)))
    vids = sorted((media_dir / "camera").glob("VID_*.mp4"))
    if vids:
        (broken / "VID_20250703_203000.mp4").write_bytes(vids[0].read_bytes()[:1500])
    (broken / "empty_voice.m4a").write_bytes(b"")
    (broken / "readme.pdf").write_bytes(b"%PDF-1.4 not really a document")

    # ---- split chat into three formats
    mar_jul = [e for e in events if e.ts < datetime(2025, 8, 1)]
    aug = [e for e in events if datetime(2025, 8, 1) <= e.ts < datetime(2025, 9, 1)]
    sep = [e for e in events if e.ts >= datetime(2025, 9, 1)]

    records: list[Any] = [_json_record(i, e) for i, e in enumerate(mar_jul, 1)]
    n_json = len(records)
    # deliberate problems: duplicates, missing/bad timestamps, unknown types, junk entries
    records.insert(40, dict(records[39]))
    records.insert(300, dict(records[299]))
    records.insert(120, {"id": "x-no-time", "sender_id": C.A, "type": "text", "text": "这条记录没有时间"})
    records.insert(121, {"id": "x-bad-time", "time": "昨天晚上", "sender_id": C.B, "type": "text", "text": "时间写错了"})
    records.insert(500, {"id": "x-red", "time": "2025-04-20 20:20:20", "sender_id": C.B, "type": "red_packet",
                         "text": "恭喜发财"})
    records.insert(501, "this is not a message object")
    records.insert(502, {"id": "x-empty", "time": "2025-04-20 20:21:00", "sender_id": C.A, "type": "text", "text": ""})
    (chat_dir / "main_chat.json").write_text(json.dumps({
        "conversation_id": "main",
        "participants": [{"id": C.A, "name": NAMES[C.A]}, {"id": C.B, "name": NAMES[C.B]}],
        "messages": records,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    with (chat_dir / "august_export.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(["id", "time", "sender_id", "sender", "type", "content", "file", "duration"])
        # overlap: last two July messages exported again (same ids) -> detected as duplicates
        for i, e in enumerate(mar_jul[-2:], n_json - 1):
            wr.writerow([f"m{i:06d}", e.ts.strftime("%Y-%m-%d %H:%M:%S"), e.sender, NAMES[e.sender], e.kind,
                         e.text or "", e.media_ref or "", e.payload.get("seconds", "")])
        for i, e in enumerate(aug, n_json + 1):
            wr.writerow([f"m{i:06d}", e.ts.strftime("%Y/%m/%d %H:%M:%S"), e.sender, NAMES[e.sender], e.kind,
                         e.text or "", e.media_ref or "", e.payload.get("seconds", "") if e.kind == "voice" else ""])
            if i == n_json + 30:
                wr.writerow(["bad-1", "", C.A, NAMES[C.A], "text", "这一行没有时间", "", ""])
                wr.writerow(["bad-2", "2025-08-05 12:00:00", C.B, NAMES[C.B], "text", "多了一列", "", "", "extra"])

    lines: list[str] = ["# 聊天记录导出（示例，全部为虚构内容）", ""]
    current = None
    for e in sep:
        if e.ts.date() != current:
            current = e.ts.date()
            lines += ["", f"———————— {current.isoformat()} ————————"]
        lines.append(_txt_line(e))
        if e.kind == "text" and rng.random() < 0.01:
            lines.append("（这一行是上一条消息的第二行）")
    (chat_dir / "september_notes.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    (chat_dir / "broken_export.jsonl").write_text("\n".join([
        json.dumps({"id": "b1", "time": "2025-09-30T23:40:00", "sender_id": C.A, "type": "text", "text": "最后一条测试"},
                   ensure_ascii=False),
        '{"id": "b2", "time": "2025-09-30T23:41:00", "sender_id": "yu", "text": "被截断的记',
        "not json at all",
        json.dumps({"id": "b3", "time": 1759247100, "sender_id": C.B, "type": "voice", "media": "voice_missing.m4a",
                    "duration": 5}, ensure_ascii=False),
    ]) + "\n", encoding="utf-8")

    (out / "README.md").write_text(
        "# Demo data (entirely fictional)\n\n"
        "Generated by `python -m memory_museum generate-demo`. The couple 林夏 & 周屿, their messages, photos, voices\n"
        "and videos are synthetic: images are procedurally drawn, voices are tone-based placeholders.\n\n"
        "It deliberately contains problems the importer must survive: duplicate records, missing and unparseable\n"
        "timestamps, an unknown message type, junk entries, references to missing files, a corrupted JPEG, a\n"
        "truncated MP4, an empty audio file, duplicate photos and an unsupported file type.\n",
        encoding="utf-8",
    )


# ------------------------------------------------------------------ stress set

def generate_stress(out: Path, *, messages: int = 300_000, photos: int = 10_000, voices: int = 1_000,
                    seed: int = 7) -> None:
    """Large synthetic archive for performance testing (tiny media files)."""
    rng = random.Random(seed)
    chat_dir, media_dir = out / "chat", out / "media"
    for d in (chat_dir, media_dir):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)
    pools = C.MORNING + C.NOON + C.AFTERNOON + C.EVENING + C.NIGHT + C.SMALLTALK
    start = datetime(2022, 1, 1, 8)
    span = (datetime(2025, 12, 31) - start).total_seconds()
    photo_every = max(1, messages // max(1, photos))
    voice_every = max(1, messages // max(1, voices))
    t = start
    step = span / messages
    with (chat_dir / "stress.jsonl").open("w", encoding="utf-8") as fh:
        i = 0
        while i < messages:
            snippet = rng.choice(pools)
            initiator = rng.choice([C.A, C.B])
            for speaker, text in snippet:
                if i >= messages:
                    break
                t += timedelta(seconds=rng.uniform(0.2, 1.8) * step)
                sender = initiator if speaker == 0 else _other(initiator)
                rec: dict[str, Any] = {"id": i, "time": t.strftime("%Y-%m-%d %H:%M:%S"), "sender_id": sender,
                                       "type": "text", "text": text}
                if i % photo_every == 0 and i // photo_every < photos:
                    name = f"IMG_{t.strftime('%Y%m%d_%H%M%S')}_{i}.jpg"
                    rec.update(type="image", media=name, text=None)
                    _tiny_photo(media_dir / "photos" / name, t, rng)
                elif i % voice_every == 1 and i // voice_every < voices:
                    name = f"voice_{i}.wav"
                    rec.update(type="voice", media=name, text=None, duration=1)
                    _tiny_wav(media_dir / "voice" / name, rng)
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                i += 1


def _tiny_photo(path: Path, taken: datetime, rng: random.Random) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    c1 = tuple(rng.randint(40, 220) for _ in range(3))
    c2 = tuple(rng.randint(40, 220) for _ in range(3))
    img = _gradient(96, 72, [(0, c1), (1, c2)])
    img.save(path, "JPEG", quality=70, exif=_exif_bytes(taken))


def _tiny_wav(path: Path, rng: random.Random) -> None:
    rate = 8000
    freq = rng.uniform(150, 400)
    pcm = b"".join(struct.pack("<h", int(3000 * math.sin(2 * math.pi * freq * i / rate))) for i in range(rate))
    write_wav(path, pcm, rate)


if __name__ == "__main__":  # pragma: no cover
    generate_demo(Path(os.environ.get("OUT", "demo-data")))
