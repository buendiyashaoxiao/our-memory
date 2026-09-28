# 我们的回忆馆 · Our Memory Museum

A private, local-first web app that turns years of a couple's chat history, photos, voice messages and videos into a quiet, browsable "memory museum" — a timeline, a *Take me back* button that opens a random day, a Sound Museum for voice messages, a time-organized photo album, favorites, hand-made Memory Moments and honest statistics.

> Real memories are the content. The software only helps reveal them.
> It never invents memories, quotes or emotional interpretations.

Everything runs on your own computer. No cloud, no accounts, no analytics, no external AI.

---

## Contents

1. [What it does](#1-what-it-does)
2. [Privacy model](#2-privacy-model)
3. [Installation](#3-installation)
4. [Windows setup](#4-windows-setup)
5. [FFmpeg](#5-ffmpeg)
6. [Running the demo](#6-running-the-demo)
7. [Importing your private data](#7-importing-your-private-data)
8. [Supported formats](#8-supported-formats)
9. [Adding a new parser](#9-adding-a-new-parser)
10. [Data directory structure](#10-data-directory-structure)
11. [Backups](#11-backups)
12. [Deleting imported data](#12-deleting-imported-data)
13. [Troubleshooting](#13-troubleshooting)
14. [Known limitations](#14-known-limitations)
15. [Running tests](#15-running-tests)

中文快速开始见 [文末](#中文快速开始)。

---

## 1. What it does

| Area | What you get |
| --- | --- |
| **Intro** | A museum-style landing page (`config/copy.json`, or override the title and lines in Settings). |
| **Timeline 时间线** | Year → month → day. *Highlights* shows days with photos, voices, videos, long conversations or favorites; *Every day* shows all. Infinite scroll, sticky month headers. |
| **Full day view** | Every message of a day (paged, 200 at a time), photo/video strip, voice list, day stats, previous/next day, hide day, add to a Memory Moment, favorite messages. |
| **随机回到一天 Take me back** | Picks a random day that actually has content (weighted toward photos, voices, videos and long chats — configurable), shows how long ago it was, real excerpts, media, stats; *再随机一天 / 前一天 / 后一天 / 查看完整当天记录*. |
| **声音博物馆 Sound Museum** | Every voice message and recording as a card: date, sender, real waveform, play/pause, previous/next (mini-player), the messages sent right before/after, favorite, your own title and private note. |
| **相册 Photos** | Grouped by month, filter photos/videos/favorites, full-screen viewer with swipe/keyboard, video playback, and **「那一天我们还说了什么」** — the real messages around the moment a photo was taken/sent. |
| **Memory Moments 回忆片段** | Create your own named collections (title, date range, description, photos, voices, messages). |
| **Favorites 收藏** | Days, photos, voices, messages and moments. |
| **Statistics 我们的数字** | Only computed from imported data: days, messages, photos, voice time, videos, busiest day/month, most common hour, longest continuous conversation, most photos in a day, first text message, most used words (Chinese-aware) and emoji, hour/month/weekday charts. No invented "compatibility scores". |
| **Review 整理与校对** | Everything the automatic photo↔message matching was unsure about; link/unlink by hand, change a photo's date, hide items. Manual decisions survive re-imports. |
| **Search** | Full-text search over messages. |
| **Settings** | Names, avatars, "which one is me", relationship start date (optional), title/intro text, language (中文/English), theme (light/dark/system), date format, Random Day weighting, autoplay (off by default), PIN lock and auto-lock, hidden days/media. |

It is mobile-first (designed for 375–430 px phone browsers) and adapts to tablets and desktop.

## 2. Privacy model

Short version (details in [docs/PRIVACY.md](docs/PRIVACY.md)):

* Your chat exports and media **stay where you put them**. The app reads them in place and never copies originals into the repository.
* Everything the app writes (database, thumbnails, converted audio, avatars) goes into one local folder: `data/` (git-ignored).
* The server listens on `127.0.0.1` only, unless you explicitly pass `--host`.
* No telemetry, analytics, CDNs, web fonts, external APIs or cloud storage. The frontend's Content-Security-Policy only allows the local server.
* `.gitignore` excludes `private-data/`, `data/`, `uploads/`, `generated/`, `cache/`, `media-derived/`, `*.db`, `.env`, `node_modules/`, `dist/` and more. The committed `demo-data/` is entirely fictional and synthetic.
* The optional PIN is an **access gate for the web page, not encryption** — anyone with access to your computer's files can read the database and your media. Use disk encryption (BitLocker / FileVault) for at-rest protection.

## 3. Installation

Requirements: **Python 3.11+**, **Node.js 18+** (only needed to build the frontend once), a modern browser. FFmpeg is bundled automatically via pip (see §5).

```bash
git clone <this repo> our-memory
cd our-memory
bash scripts/setup.sh          # macOS / Linux — creates .venv, installs deps, builds the frontend
```

Manual equivalent:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cd frontend && npm ci && npm run build && cd ..
.venv/bin/python -m memory_museum doctor    # checks ffmpeg, jieba, frontend build
```

(`requirements.txt` includes test tools; runtime-only installs can use `pip install .` or `pip install ".[zh]"` for better Chinese word statistics.)

## 4. Windows setup

In **PowerShell**, from the repository folder:

```powershell
# one-time
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1

# demo (opens the browser)
.\.venv\Scripts\python.exe -m memory_museum demo --open
```

Manual steps if you prefer:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd frontend; npm ci; npm run build; cd ..
.\.venv\Scripts\python.exe -m memory_museum doctor
```

Notes for Windows:

* Install Python from python.org (tick *Add python.exe to PATH*) and Node.js LTS from nodejs.org.
* Paths with spaces must be quoted: `--chat "D:\My Backup\chat"`.
* Chat exports saved by Chinese Windows tools in GBK/GB18030 are detected automatically.
* If PowerShell refuses scripts, use `-ExecutionPolicy Bypass` as shown (applies only to that one command).

## 5. FFmpeg

FFmpeg is used for video thumbnails, audio/video durations and codecs, real voice waveforms, and converting formats browsers can't play (e.g. WeChat-style `.amr`) into `.m4a`.

**You normally don't need to install anything**: the `imageio-ffmpeg` pip package ships a static ffmpeg binary for Windows, macOS and Linux. Lookup order:

1. `MEMORY_MUSEUM_FFMPEG` / `MEMORY_MUSEUM_FFPROBE` environment variables
2. `ffmpeg` / `ffprobe` on your `PATH`
3. the bundled `imageio-ffmpeg` binary

To use a system install instead: Windows `winget install Gyan.FFmpeg`, macOS `brew install ffmpeg`, Debian/Ubuntu `sudo apt install ffmpeg`.

Without any ffmpeg the app still works: photos are fully supported (Pillow), WAV durations/waveforms are read natively, other audio/video simply lack duration, thumbnails and waveforms. `python -m memory_museum doctor` tells you what was found.

## 6. Running the demo

```bash
.venv/bin/python -m memory_museum demo --open      # Windows: .\.venv\Scripts\python.exe -m memory_museum demo --open
```

This imports the fictional couple 林夏 & 周屿 (`demo-data/`, ~4,000 messages over 7 months, ~130 photos, ~46 voice clips, videos, and deliberately broken records) into `data/demo/` and serves it at <http://127.0.0.1:8765/>. `--reset` re-imports from scratch; `--no-serve` only imports.

A larger synthetic **stress-test** dataset (default 300,000 messages, 10,000 photos, 1,000 voices) can be generated on demand into the git-ignored `demo-data-stress/`:

```bash
.venv/bin/python -m memory_museum generate-demo --stress
.venv/bin/python -m memory_museum import --data-dir data/stress --chat demo-data-stress/chat --media demo-data-stress/media --yes
.venv/bin/python -m memory_museum serve --data-dir data/stress
```

(On the development machine this import took ~55 s and every API endpoint answered in under 30 ms.)

For frontend development with hot reload: `bash scripts/dev.sh` (or `scripts\dev.ps1`), then open <http://127.0.0.1:5173/>.

## 7. Importing your private data

1. Create the private folders (git-ignored):

   ```bash
   .venv/bin/python -m memory_museum init
   ```

2. Put your exports there (or anywhere else — paths are just arguments):

   ```
   private-data/
     chat/     ← JSON / JSONL / CSV / TXT exports (sub-folders are fine)
     media/    ← photos, voice messages, recordings, videos (any folder structure)
   ```

3. Import. You get a **preview** first and decide whether to keep it:

   ```bash
   .venv/bin/python -m memory_museum import --chat private-data/chat --media private-data/media
   ```

   ```
   Detected (in the museum after this import):
     125,482 messages
     8,203 images
     1,482 voice messages, 37 other audio
     221 videos
   Date range:
     2023-04-17 -> 2026-09-28
   Participants:
     ...
   Media associations:
     Exact: ...   High confidence: ...   Medium confidence: ...
     Low (suggestion only, not linked): ...   Unlinked media files: ...
   Warnings:
     missing timestamp: 3 ... unknown type: 1 ... corrupt: IMG_x.jpg ...
   Save this import into the museum? [y/N]
   ```

   Answer `n` to discard it (nothing changes), fix your inputs and run it again. Useful flags: `--dry-run` (preview only), `--yes` (no question), `--report report.json` (full JSON report), `--parser json|csv|txt` (force a parser), `--conversation <id>`, `--timezone Asia/Shanghai`.
   Separate steps also exist: `import-chat --input ...`, `import-media --input ...`, `build-index`.

4. Start the museum:

   ```bash
   .venv/bin/python -m memory_museum serve --open
   ```

5. Open **Settings** to set your names, avatars, which person is you, and optionally a PIN. Open **整理与校对 / Review** to confirm uncertain photo↔message matches.

Re-importing is safe and incremental: duplicate messages are skipped, unchanged media files are not re-processed, and your favorites, titles, notes, moments, hidden items and manual links are kept.

**Viewing on your phone**: the phone must reach your computer over your home Wi-Fi. Set a PIN first, then `serve --host 0.0.0.0` and open `http://<your-computer's-LAN-IP>:8765/` on the phone. Only do this on a network you trust (traffic is plain HTTP inside your LAN).

## 8. Supported formats

Chat (details and examples in [docs/IMPORT_FORMATS.md](docs/IMPORT_FORMATS.md)):

| Parser | Files | Shape |
| --- | --- | --- |
| `json` | `.json`, `.jsonl`, `.ndjson` | array of messages, `{"messages": [...], "participants": [...]}`, or one JSON object per line (best for huge archives) |
| `csv` | `.csv`, `.tsv` | header row; column names matched against common aliases in English and Chinese (`time/时间`, `sender/发送者`, `text/内容`, `type/类型`, `file/附件`, `id`, `reply_to` …) |
| `txt` | `.txt`, `.log` | `2024-03-01 21:03:15 Name: text`, `[date time] Name：text`, block style (header line then message lines), `—— 2024-03-01 ——` date lines followed by `21:03 Name: text`, WhatsApp-style `01/03/2024, 21:03 - Name: text` |

Message types: text, image, voice, audio, video, sticker, file, link, system, unknown. Media markers such as `[图片] IMG_1.jpg`, `[语音] v.m4a 8"`, `<Media omitted>` are recognised. Timestamps: ISO 8601 (with or without timezone), `YYYY/M/D H:MM`, `2024年3月1日 下午3:05`, AM/PM, Unix seconds/milliseconds; ambiguous `03/04/2024` is resolved per file or reported.

Media: photos `jpg jpeg png webp gif bmp` (HEIC is detected but must be converted to JPEG first), audio `mp3 wav m4a aac ogg opus flac amr wma caf`, video `mp4 mov m4v 3gp webm mkv avi`. Capture time comes from EXIF → video metadata → filename (`IMG_20230417_203015`, `PXL_…`, `Screenshot 2023-04-17 at …`, `IMG-20230417-WA0001`, `mmexport<ms>`) → file modification time (marked as unreliable).

## 9. Adding a new parser

Write a class with `name`, `extensions`, `sniff()` and `parse()` that yields `ParsedMessage` objects, then add it to `PARSERS` in `memory_museum/parsers/__init__.py`. Step-by-step guide with a complete example: [docs/ADDING_A_PARSER.md](docs/ADDING_A_PARSER.md).

## 10. Data directory structure

```
our-memory/
  memory_museum/        Python package (CLI, importer, parsers, media, association, API)
  frontend/             React + TypeScript + Vite app (npm run build → frontend/dist)
  config/copy.json      default intro/landing text (zh + en)
  demo-data/            fictional demo dataset (committed)
  docs/                 architecture, formats, privacy, parser guide
  tests/                pytest suite + corrupted input fixtures
  scripts/              setup / dev helpers for Windows and macOS/Linux

  private-data/         (git-ignored) suggested place for your exports
  data/                 (git-ignored) everything the app writes:
    museum.db             SQLite database (messages, media index, your curation, settings)
    museum.staging.db     temporary copy during an import preview
    cache/thumbs/         JPEG thumbnails (named by content hash)
    cache/playable/       browser-friendly copies of .amr/.wma voice files
    avatars/              avatars you uploaded (re-encoded, EXIF stripped)
    demo/                 the demo museum (same layout)
```

The data folder can be moved with `--data-dir <path>` or the `MEMORY_MUSEUM_DATA` environment variable.

## 11. Backups

What matters, in order:

1. **Your original exports and media** — back them up like any precious files; the museum never modifies them.
2. **`data/museum.db`** — contains everything *you* added (favorites, titles, notes, moments, hidden items, manual links, settings). Back it up while the server is stopped, or safely while running with:

   ```bash
   sqlite3 data/museum.db ".backup 'museum-backup.db'"
   ```

   (Or just copy `museum.db` after stopping the server.)
3. `data/cache/` and `data/avatars/` can always be regenerated/re-uploaded.

To restore, put `museum.db` back into `data/` and run `python -m memory_museum build-index`. If your media folders moved, run `import-media` again with the new path — the old entries are marked missing; manual notes are attached to the old paths, so keep media paths stable where you can.

## 12. Deleting imported data

```bash
.venv/bin/python -m memory_museum purge            # asks for confirmation
.venv/bin/python -m memory_museum purge --data-dir data/demo --yes
```

This deletes the database, the staging database, thumbnails, converted audio and avatars in the data folder. **It never deletes your original chat exports or media files.** To remove every trace, also delete the `data/` folder and your `private-data/` folder yourself.

## 13. Troubleshooting

| Problem | Fix |
| --- | --- |
| Browser shows *API is running, but the frontend has not been built yet* | `cd frontend && npm ci && npm run build`, then restart `serve`. |
| Page says it cannot reach the local server | Is `python -m memory_museum serve` still running? Same port? |
| Port already in use | `serve --port 8800` |
| No video thumbnails / durations | `python -m memory_museum doctor` → install `imageio-ffmpeg` or a system ffmpeg (§5), then `import-media` again. |
| Chinese text looks garbled | The file is in an unusual encoding; re-save it as UTF-8. UTF-8 (with/without BOM) and GB18030/GBK are detected automatically. |
| Many "bad timestamp" warnings | Check the date format in [docs/IMPORT_FORMATS.md](docs/IMPORT_FORMATS.md); for `dd/mm/yyyy` vs `mm/dd/yyyy` files where every day ≤ 12, write a small parser or convert to ISO dates. |
| Everything happens a few hours off | Timestamps that carry a UTC offset (or Unix epochs) are converted to your computer's zone. Re-import with `--timezone Asia/Shanghai` (or `--timezone UTC+8`; on Windows IANA names need `pip install tzdata`). |
| The same person appears twice | Different exports identify people differently. A name-only sender ("林夏") is merged automatically into an id-based one ("xia" named 林夏) when unambiguous. Otherwise give both the same display name in Settings (they stay separate in per-person statistics). |
| A photo is linked to the wrong message | Review → *Unlink* / *Pick the matching message*. Manual choices are never overwritten. |
| A voice message won't play | Browsers can't play some formats (e.g. `.silk`). `.amr`/`.wma` are converted automatically when ffmpeg is available. |
| A video shows "this browser cannot decode" | The file is fine but your browser lacks the codec (e.g. HEVC on Chrome/Windows). Use Safari/Edge or *Open original file*. |
| Forgot the PIN | Stop the server, run `python -m memory_museum clear-pin`, start again. |
| `pip install jieba` fails | Optional. Word statistics fall back to a simpler method; everything else works. |

## 14. Known limitations

* **Chat formats**: only generic JSON/CSV/TXT adapters ship in this first version; app-specific exporters (WeChat, iMessage, Telegram, LINE …) need small parsers (see §9) or conversion.
* **HEIC/HEIF** photos and **`.silk`** voice files are detected but not displayed/playable; convert them first.
* **Videos** are not transcoded. H.264 MP4/MOV plays in all mainstream browsers; HEVC may not play in Chrome on Windows.
* **Timezones**: naive timestamps are treated as local wall-clock time; a trip abroad keeps the times as exported. Video `creation_time` is assumed to be UTC (as per the MP4 spec), which some cameras violate.
* **Fuzzy matching** only pairs a file with a media-type message (e.g. `[图片]`) sent within 30 minutes; photos shared much later stay unlinked (by design) and appear in the gallery by capture date.
* **Duplicates without message IDs**: two genuinely identical messages in the same minute are both kept; exact duplicates are detected across re-imports, but not across *different* export formats of the same chat when one has IDs and the other doesn't.
* **Security**: the PIN is not encryption (see §2). There is no HTTPS; LAN access is plain HTTP.
* **Speech-to-text** is not included. The data model keeps voice metadata separate so a local, optional transcription module can be added later.
* **Test browser**: Playwright's bundled open-source Chromium cannot decode AAC/H.264, so the end-to-end test plays an MP3 voice and only checks that videos open; real Chrome/Edge/Safari play them.
* Very large single `.json` documents are loaded into memory at once; use JSON Lines for archives in the hundreds of MB.

## 15. Running tests

```bash
# backend unit + integration tests (≈10 s)
.venv/bin/python -m pytest

# frontend unit/component tests
cd frontend && npm test

# frontend type check + production build
npm run build

# end-to-end smoke test (starts the real server on the demo data; needs a Chromium for Playwright)
npx playwright install chromium     # once, if you don't already have it
npm run e2e
```

The e2e test walks: launch → intro → timeline → a day → photo full-screen + surrounding chat → a video → Random Day (again / previous) → Sound Museum playback, plus a check that broken/missing media degrade gracefully.

---

## 中文快速开始

```powershell
# Windows PowerShell（第一次）
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
# 先看示例（完全虚构的数据）
.\.venv\Scripts\python.exe -m memory_museum demo --open
```

1. `python -m memory_museum init` 会创建 `private-data/chat` 和 `private-data/media`（这两个文件夹不会被 git 提交）。
2. 把聊天记录导出文件放进 `chat`，把照片、语音、视频放进 `media`。
3. `python -m memory_museum import --chat private-data/chat --media private-data/media`：先看预览，确认后再保存；不满意就选 `n`，什么都不会改变。
4. `python -m memory_museum serve --open` 打开回忆馆。
5. 在「设置」里填名字、头像、"这是我"，可以设置 PIN；在「整理与校对」里确认那些不确定的照片对应关系。

所有数据只在这台电脑上。PIN 只是网页门锁，不是加密。删除导入的数据：`python -m memory_museum purge`（不会删除你的原始文件）。
