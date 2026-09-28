import argparse
import os
import re
import subprocess
import sys
import tempfile
from multiprocessing import Pool

import imageio_ffmpeg
import librosa
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FPS = 24
OUT_W, OUT_H = 1280, 720
W, H = 640, 360  # scene is rendered at half resolution; everything in it is soft anyway
BAR = 64
FONT_PATH = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

# (start_sec, top, bottom, glow, particle tint, density, stars, rays, wave)
SECTIONS = [
    (0.0,   (3, 4, 12),   (10, 12, 30),  (60, 80, 160),   (180, 200, 255), 0.15, 1.0, 0.0, 0.3),
    (13.0,  (5, 8, 25),   (20, 30, 70),  (80, 110, 200),  (170, 200, 255), 0.35, 0.9, 0.0, 0.7),
    (64.3,  (25, 10, 40), (90, 40, 90),  (230, 120, 160), (255, 190, 210), 0.75, 0.4, 0.2, 1.0),
    (104.5, (4, 4, 10),   (15, 12, 30),  (120, 100, 160), (220, 210, 255), 0.10, 0.8, 0.0, 0.4),
    (112.4, (6, 18, 30),  (25, 60, 80),  (90, 180, 190),  (190, 240, 240), 0.45, 0.6, 0.0, 0.8),
    (159.8, (35, 15, 10), (120, 62, 30), (255, 180, 90),  (255, 220, 160), 1.00, 0.2, 1.0, 1.0),
    (219.8, (10, 6, 18),  (40, 25, 50),  (200, 140, 170), (255, 210, 220), 0.30, 1.0, 0.0, 0.5),
]
XFADE = 2.5


def smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def section_params(t):
    idx = 0
    for i, s in enumerate(SECTIONS):
        if t >= s[0]:
            idx = i
    cur = SECTIONS[idx]
    if idx == 0:
        return cur
    prev = SECTIONS[idx - 1]
    k = float(smoothstep((t - cur[0] + XFADE / 2) / XFADE))
    out = [cur[0]]
    for a, b in zip(prev[1:], cur[1:]):
        if isinstance(a, tuple):
            out.append(tuple(x + (y - x) * k for x, y in zip(a, b)))
        else:
            out.append(a + (b - a) * k)
    return out


def analyze(audio_path):
    y, sr = librosa.load(audio_path, sr=22050, mono=True)
    duration = len(y) / sr
    hop = 512
    ft = librosa.frames_to_time(np.arange(1 + len(y) // hop), sr=sr, hop_length=hop)
    n = int(duration * FPS)
    tt = np.arange(n) / FPS

    rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    rms = np.interp(tt, ft[: len(rms)], rms)
    rms = rms / (np.percentile(rms, 98) + 1e-9)

    onset = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
    onset = np.interp(tt, ft[: len(onset)], onset)
    onset = onset / (np.percentile(onset, 99) + 1e-9)

    mel = librosa.power_to_db(librosa.feature.melspectrogram(y=y, sr=sr, hop_length=hop, n_mels=48), ref=np.max)
    mel = np.clip((mel + 70) / 70, 0, 1)
    mel = np.stack([np.interp(tt, ft[: mel.shape[1]], m) for m in mel], axis=1)

    _, beats = librosa.beat.beat_track(y=y, sr=sr, hop_length=hop)
    beat_times = librosa.frames_to_time(beats, sr=sr, hop_length=hop)
    beat = np.zeros(n)
    for b in beat_times:
        i0 = int(b * FPS)
        if i0 >= n:
            continue
        seg = np.arange(i0, min(n, i0 + FPS))
        beat[seg] = np.maximum(beat[seg], np.exp(-(seg / FPS - b) / 0.25))

    # asymmetric smoothing: fast attack, slow release
    def env(x, att=0.5, rel=0.08):
        o = np.zeros_like(x)
        for i in range(1, len(x)):
            a = att if np.all(x[i] > o[i - 1]) else rel
            o[i] = o[i - 1] + (x[i] - o[i - 1]) * a
        return o

    rms_s = env(rms, 0.3, 0.05)
    mel_s = np.zeros_like(mel)
    for i in range(1, len(mel)):
        mel_s[i] = mel_s[i - 1] + (mel[i] - mel_s[i - 1]) * np.where(mel[i] > mel_s[i - 1], 0.5, 0.1)
    return dict(duration=duration, n=n, rms=np.clip(rms_s, 0, 1.5), onset=np.clip(onset, 0, 1.5),
                mel=mel_s, beat=beat)


def parse_lrc(path):
    if not path:
        return []
    lines = []
    pat = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\]")
    with open(path, encoding="utf-8") as f:
        for raw in f:
            stamps = pat.findall(raw)
            text = pat.sub("", raw).strip()
            for m, s in stamps:
                lines.append([int(m) * 60 + float(s), text])
    lines.sort()
    out = []
    for i, (st, text) in enumerate(lines):
        end = lines[i + 1][0] if i + 1 < len(lines) else st + 6
        if text:
            out.append((st, min(end, st + 8), text))
    return out


class Scene:
    def __init__(self, feats, lyrics, title):
        self.f = feats
        self.lyrics = lyrics
        self.title = title
        rng = np.random.default_rng(7)

        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        self.grad = (yy / (H - 1))[..., None]
        d = ((xx - W * 0.5) / W) ** 2 + ((yy - H * 0.78) / H) ** 2
        self.center_glow = np.exp(-d / 0.06)[..., None]
        vx, vy = (xx - W / 2) / (W / 2), (yy - H / 2) / (H / 2)
        self.vignette = np.clip(1.0 - 0.35 * (vx ** 2 + vy ** 2) ** 1.2, 0.35, 1.0)[..., None]
        self.ray_ang = np.arctan2(yy + H * 0.25, xx - W * 0.55)
        self.ray_fall = np.exp(-np.hypot(xx - W * 0.55, yy + H * 0.25) / (H * 0.9))

        self.stars = np.column_stack([rng.uniform(0, W, 320), rng.uniform(0, H * 0.7, 320),
                                      rng.uniform(0.2, 1.0, 320), rng.uniform(0, 6.28, 320),
                                      rng.uniform(0.5, 2.5, 320)])

        n = 240
        self.p_x0 = rng.uniform(0, W, n)
        self.p_y0 = rng.uniform(0, H, n)
        self.p_z = rng.uniform(0.25, 1.0, n) ** 1.5
        self.p_u = rng.uniform(0, 1, n)
        self.p_ph = rng.uniform(0, 6.28, n)
        self.p_hue = rng.uniform(-25, 25, (n, 3))
        self.sprites = {r: self._sprite(r) for r in range(2, 34)}

        self.grain = [rng.normal(0, 2.5, (OUT_H, OUT_W, 1)).astype(np.int16) for _ in range(6)]
        self.text_cache = {}
        self.font_lyric = ImageFont.truetype(FONT_PATH, 38)
        self.font_title = ImageFont.truetype(FONT_PATH, 30)

    @staticmethod
    def _sprite(r):
        s = 2 * r + 3
        yy, xx = np.mgrid[0:s, 0:s].astype(np.float32)
        d = np.hypot(xx - s / 2 + 0.5, yy - s / 2 + 0.5)
        disc = np.clip((r - d) / 1.2 + 0.5, 0, 1)
        rim = np.exp(-((d - r * 0.85) ** 2) / (r * 0.12 + 0.5) ** 2) * 0.35
        core = np.exp(-(d ** 2) / (r * r * 0.4))
        return ((disc * 0.45 + rim * disc + core * 0.3))[..., None].astype(np.float32)

    def _blit(self, img, spr, cx, cy, color):
        s = spr.shape[0]
        x0, y0 = int(cx - s / 2), int(cy - s / 2)
        x1, y1 = x0 + s, y0 + s
        sx0, sy0 = max(0, -x0), max(0, -y0)
        sx1, sy1 = s - max(0, x1 - W), s - max(0, y1 - H)
        if sx1 <= sx0 or sy1 <= sy0:
            return
        img[max(0, y0):min(H, y1), max(0, x0):min(W, x1)] += spr[sy0:sy1, sx0:sx1] * color

    def _text_layer(self, text, font, spacing=0):
        key = (text, id(font))
        if key in self.text_cache:
            return self.text_cache[key]
        layer = Image.new("L", (OUT_W, 120), 0)
        dr = ImageDraw.Draw(layer)
        if spacing:
            widths = [dr.textlength(ch, font=font) for ch in text]
            total = sum(widths) + spacing * (len(text) - 1)
            x = (OUT_W - total) / 2
            for ch, w in zip(text, widths):
                dr.text((x, 60), ch, font=font, fill=255, anchor="lm")
                x += w + spacing
        else:
            dr.text((OUT_W / 2, 60), text, font=font, fill=255, anchor="mm")
        glow = np.asarray(layer.filter(ImageFilter.GaussianBlur(10)), dtype=np.float32) / 255
        sharp = np.asarray(layer, dtype=np.float32) / 255
        self.text_cache[key] = (sharp[..., None], glow[..., None])
        return self.text_cache[key]

    def _overlay_text(self, frame, text, font, alpha, y_center, color, spacing=0, glow_color=None):
        if alpha <= 0.01:
            return
        sharp, glow = self._text_layer(text, font, spacing)
        y0 = int(y_center - 60)
        region = frame[y0:y0 + 120]
        gc = np.array(glow_color if glow_color is not None else color, dtype=np.float32)
        region *= 1 - np.clip(glow * 2.2, 0, 1) * 0.55 * alpha
        region += glow * gc * 0.35 * alpha
        a = sharp * alpha
        region *= (1 - a)
        region += a * np.array(color, dtype=np.float32)

    def render(self, i):
        f = self.f
        t = i / FPS
        _, top, bot, glow_c, tint, density, star_amt, rays, wave_amt = section_params(t)
        rms, beat, onset = f["rms"][i], f["beat"][i], f["onset"][i]
        top, bot, glow_c, tint = (np.array(c, dtype=np.float32) / 255 for c in (top, bot, glow_c, tint))

        img = top + (bot - top) * self.grad
        img = img + self.center_glow * glow_c * (0.18 + 0.45 * rms + 0.12 * beat)

        if rays > 0.01:
            m = (0.5 + 0.5 * np.sin(self.ray_ang * 23 + t * 0.35)) ** 6
            m *= (0.5 + 0.5 * np.sin(self.ray_ang * 9 - t * 0.21)) ** 2
            img += (m * self.ray_fall)[..., None] * glow_c * rays * (0.35 + 0.35 * rms)

        if star_amt > 0.01:
            sx, sy, sb, sp, sf = self.stars.T
            tw = sb * (0.55 + 0.45 * np.sin(t * sf + sp)) * star_amt
            xi, yi = sx.astype(int), sy.astype(int)
            np.add.at(img, (yi, xi), (tw[:, None] * np.array([0.85, 0.9, 1.0])).astype(np.float32))

        z = self.p_z
        vis = smoothstep((density - self.p_u) / 0.08 + 0.5)
        py = (self.p_y0 - t * (4 + z * 14)) % (H + 80) - 40
        px = (self.p_x0 + np.sin(t * 0.3 + self.p_ph) * 18 * z + t * 2) % (W + 80) - 40
        pulse = 1 + 0.5 * beat * z + 0.3 * onset
        radii = np.clip((2 + z * 16) * (1 + 0.12 * beat), 2, 33).astype(int)
        bright = (0.05 + 0.22 * z) * (0.6 + 0.7 * rms) * pulse * vis
        for k in np.nonzero(vis > 0.01)[0]:
            col = np.clip(tint + self.p_hue[k] / 255, 0, 1) * bright[k]
            self._blit(img, self.sprites[radii[k]], px[k], py[k], col.astype(np.float32))

        if wave_amt > 0.01:
            spec = f["mel"][i]
            half = np.concatenate([spec[::-1], spec])
            xs = np.linspace(0, W, 160)
            vals = np.interp(np.linspace(0, len(half) - 1, 160), np.arange(len(half)), half)
            base = H * 0.80
            layer = Image.new("L", (W, H), 0)
            dr = ImageDraw.Draw(layer)
            amp = 55 * wave_amt * (0.4 + 0.6 * rms)
            dr.line(list(zip(xs, base - vals ** 1.5 * amp)), fill=255, width=2)
            dr.line(list(zip(xs, base + vals ** 1.5 * amp * 0.35)), fill=110, width=1)
            sharp = np.asarray(layer, dtype=np.float32)[..., None] / 255
            blur = np.asarray(layer.filter(ImageFilter.GaussianBlur(6)), dtype=np.float32)[..., None] / 255
            img += (sharp * 0.7 + blur * 2.2) * glow_c * wave_amt

        img *= self.vignette
        img = 1 - np.exp(-img * 1.6)
        fade = min(1.0, t / 2.5, max(0.0, (f["duration"] - t) / 3.0))
        img *= fade

        small = Image.fromarray(np.clip(img * 255, 0, 255).astype(np.uint8))
        frame = np.asarray(small.resize((OUT_W, OUT_H), Image.BILINEAR), dtype=np.float32)

        lyric_y = OUT_H - BAR - 58
        for st, en, text in self.lyrics:
            if st - 0.5 <= t <= en + 0.5:
                a = min(smoothstep((t - st + 0.3) / 0.6), smoothstep((en - t + 0.2) / 0.6))
                self._overlay_text(frame, text, self.font_lyric, float(a) * fade,
                                   lyric_y - 8 * (1 - a), (250, 245, 240), glow_color=tuple(glow_c * 255))
        if self.title:
            for st, en in ((2.0, 11.5), (f["duration"] - 14, f["duration"] - 3.5)):
                if st <= t <= en:
                    a = min(smoothstep((t - st) / 2.0), smoothstep((en - t) / 2.0))
                    self._overlay_text(frame, self.title, self.font_title, float(a), OUT_H / 2,
                                       (235, 230, 240), spacing=18, glow_color=tuple(glow_c * 255))

        out = np.clip(frame, 0, 255).astype(np.int16) + self.grain[i % len(self.grain)]
        out = np.clip(out, 0, 255).astype(np.uint8)
        out[:BAR] = 0
        out[-BAR:] = 0
        return out


_scene = None


def _init(feats, lyrics, title):
    global _scene
    _scene = Scene(feats, lyrics, title)


def _render_chunk(args):
    start, end, path = args
    cmd = [FFMPEG, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{OUT_W}x{OUT_H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264",
           "-preset", "medium", "-crf", "21", "-pix_fmt", "yuv420p", path]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(start, end):
        p.stdin.write(_scene.render(i).tobytes())
    p.stdin.close()
    p.wait()
    return path


def main():
    ap = argparse.ArgumentParser(description="Render an audio-reactive music video.")
    ap.add_argument("audio")
    ap.add_argument("-o", "--out", default="mv.mp4")
    ap.add_argument("--lrc", help="optional LRC lyrics file for subtitles")
    ap.add_argument("--title", default="our memory")
    ap.add_argument("--jobs", type=int, default=os.cpu_count())
    ap.add_argument("--preview", type=float, nargs=2, metavar=("START", "END"),
                    help="render only this time range (seconds)")
    ap.add_argument("--still", type=float, action="append", default=[],
                    help="save a PNG frame at this time instead of rendering video")
    a = ap.parse_args()

    feats = analyze(a.audio)
    lyrics = parse_lrc(a.lrc)

    if a.still:
        _init(feats, lyrics, a.title)
        for s in a.still:
            Image.fromarray(_scene.render(int(s * FPS))).save(f"still_{s:06.1f}.png")
        return

    first, last = 0, feats["n"]
    if a.preview:
        first, last = int(a.preview[0] * FPS), min(feats["n"], int(a.preview[1] * FPS))

    tmp = tempfile.mkdtemp(prefix="mv_")
    step = -(-(last - first) // (a.jobs * 4))
    chunks = [(s, min(last, s + step), os.path.join(tmp, f"c{k:04d}.mp4"))
              for k, s in enumerate(range(first, last, step))]
    with Pool(a.jobs, initializer=_init, initargs=(feats, lyrics, a.title)) as pool:
        for k, _ in enumerate(pool.imap(_render_chunk, chunks), 1):
            print(f"\r{k}/{len(chunks)} chunks", end="", file=sys.stderr, flush=True)
    print(file=sys.stderr)

    listing = os.path.join(tmp, "list.txt")
    with open(listing, "w") as fh:
        fh.writelines(f"file '{c[2]}'\n" for c in chunks)
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", listing,
                    "-ss", str(first / FPS), "-t", str((last - first) / FPS), "-i", a.audio,
                    "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-shortest", "-movflags", "+faststart", a.out], check=True)
    print(a.out)


if __name__ == "__main__":
    main()
