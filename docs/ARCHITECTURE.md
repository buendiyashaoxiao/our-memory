# Architecture

A single local process: a Python package that imports data into SQLite and serves a JSON API plus a static React build. No external services.

```
 exports & media (read-only, stay where they are)
        │
        ▼
 ┌──────────────── memory_museum (Python 3.11) ────────────────┐
 │ parsers/*      → normalized ParsedMessage stream             │
 │ importer.py    → batched INSERT OR IGNORE (dedupe keys)      │
 │ media/scanner  → parallel metadata, thumbnails, waveforms    │
 │ association.py → exact + conservative time matching          │
 │ index.py       → day_summary + cached statistics             │
 │ pipeline.py    → staged import → preview → commit / discard  │
 │ api/app.py     → FastAPI on 127.0.0.1, optional PIN gate     │
 └───────────────────────┬──────────────────────────────────────┘
                         │ SQLite (data/museum.db) + data/cache/
                         ▼
 frontend/ (React + TypeScript + Vite) → built into frontend/dist, served by the same process
```

## Why this stack

* **Python + SQLite** — one file database, no server, works identically on Windows/macOS/Linux, handles hundreds of thousands of rows with plain indexes. Raw `sqlite3` (no ORM) keeps queries explicit and fast.
* **FastAPI** — small, typed, serves files with HTTP range support (needed for seeking in audio/video).
* **Pillow** for images/EXIF; **ffmpeg** (system, or the static binary shipped by `imageio-ffmpeg`) for audio/video — so Windows users don't need to install ffmpeg by hand.
* **React + TypeScript + Vite** with only `react-router-dom` as a runtime dependency. Custom CSS (no UI framework, no web fonts, no CDN) keeps the look intentional and the app fully offline.

## Data model (`memory_museum/db.py`)

Imported facts:

| table | purpose |
| --- | --- |
| `messages` | normalized chat messages. `ts` is a naive local ISO string, `day`/`hour` are denormalized for indexes. `dedupe_key` is UNIQUE. `metadata` keeps unrecognised source fields (nothing is silently discarded). |
| `participants`, `conversations` | derived from messages |
| `media` | one row per file: path (absolute, never copied), type, hash, capture time + where it came from (`ts_source`: exif / media_meta / filename / filename_date / mtime / chat / manual), duration, dimensions, codec, status (ok / corrupt / missing / unsupported), thumbnail/playable cache paths, real waveform peaks, and the association (`message_id`, `association_method`, `association_confidence`, `suggested_message_id`, `association_locked`). |
| `import_runs` | JSON report of every import |

User curation (never overwritten by imports): `favorites`, `moments` + `moment_items`, `hidden_days`, media `user_title`/`user_note`/`hidden`/manual dates and links, `settings`.

Derived: `day_summary` (per-day counts, first/last message, longest continuous conversation, activity score) and `stats_cache`. Both are rebuilt by `build-index` and refreshed incrementally when you hide something or change a date.

## Import pipeline

1. **Parse** — each file goes to the parser with the highest `sniff()` score. Parsers stream `ParsedMessage` objects and record problems on an `ImportReport` (malformed rows, missing/bad timestamps, unknown types, unreadable files) instead of raising.
2. **Store** — batches of 5,000 `INSERT OR IGNORE`. The dedupe key is the export's own message id when present; otherwise a hash of (conversation, time, sender, type, text, media reference) plus the occurrence index within the file, so genuine repeats ("好", "好") survive while re-imports don't duplicate.
3. **Post-process** — resolve replies, merge name-only senders into id-based participants when unambiguous.
4. **Media** — walk folders, skip unchanged files (size + mtime), extract metadata in a thread pool, generate 640 px JPEG thumbnails (named by content hash so duplicates share one), video poster frames, waveform peaks (48 buckets decoded at 2 kHz), and `.m4a` copies of `.amr`/`.wma`. Files that disappeared are marked `missing`, not deleted. Byte-identical files are marked `duplicate_of` and shown once.
5. **Associate** (below), **index**, **preview**.

Staging: the whole pipeline runs against `museum.staging.db`, a copy of the live database made with SQLite's backup API. *Commit* copies it back with the same API (safe while the server runs); *discard* deletes it.

## Association engine (`association.py`)

1. Reset automatic decisions (idempotent), keep `association_locked` rows.
2. **Exact**: a message's media reference (basename, case-insensitive; stem if the reference has no extension) names exactly one file → `exact`. Several same-named files that are byte-identical copies → still `exact` (canonical copy). Several different files → closest in time, confidence `high`, method `filename_time`.
3. **Time proximity** for media-type messages without a usable reference: candidate pairs of compatible kinds (image↔image, video↔video, voice/audio↔voice/audio) within 30 minutes, scored:
   * ≤ 2 min → `high`, ≤ 10 min → `medium`, ≤ 30 min → `low`
   * downgraded one level if the file's time came from mtime or a date-only filename
   * downgraded one level if another candidate is within 60 s of the best one (ambiguity)
   * greedy one-to-one assignment, closest pairs first.
4. Only `high`/`medium` are applied. `low` is stored as `suggested_message_id` for the Review screen, never shown as a fact.
5. Files without a trustworthy capture time adopt the send time of an `exact`/`high` linked message (`ts_source = chat`).

## Timeline, Random Day, stats

* **Curated timeline** = days with any photo/video/voice, ≥ 30 messages, a favorite, or a moment starting that day. Cursor pagination by day.
* **Excerpts** are real messages chosen for readability (4–120 characters, spread across the day, favorites first). No summarisation, no rewriting.
* **Random Day** samples from days with ≥ `min_messages` messages or any media, excluding hidden days and the current day. Weight = `1 + 0.6·photo·min(photos,10) + 0.8·voice·min(voices,6) + 1.2·video·min(videos,4) + conversation·min(messages/40, 5)`; uniform mode is available.
* **Statistics** are read from `day_summary`/`messages` and cached. Word counts use `jieba` when installed (stop-words removed), otherwise 2-character pairs; the UI says which.

## API

All under `/api` (see `memory_museum/api/app.py`): `overview`, `timeline`, `timeline/years`, `days/{day}`, `days/{day}/messages`, `random-day`, `sounds`, `gallery`, `gallery/months`, `media/{id}` (+ `/file`, `/thumb`, `/context`, `/candidates`, `/link`), `messages/{id}`, `search`, `favorites`, `moments`, `stats`, `review/*`, `settings`, `copy`, `lock/*`. Files are only ever served from paths recorded by the importer (no user-supplied paths). Responses are `Cache-Control: no-store` except thumbnails/media (private cache).

## Security model

Optional PIN stored as salted PBKDF2-SHA256 (240k iterations). Unlocking creates a random session token (HttpOnly, SameSite=Strict cookie) kept in memory only; an HTTP middleware rejects every `/api` request (including media files) without a valid session. Idle sessions expire after the configured auto-lock time; five wrong PINs trigger a 30 s lockout. This protects against someone opening the page, not against reading files on disk — see PRIVACY.md.

**Extension point for encryption at rest**: all file access goes through `db.connect()` and the media/thumbnail handlers in `api/app.py`, so a future version can swap in SQLCipher and an encrypted cache without touching the rest of the code.

## Frontend

`src/lib` (typed API client, formatting, zh/en strings, app context, a single shared audio player), `src/components` (thumbnails with lazy loading and graceful failure, waveform player, chat list, lightbox, bottom sheets), `src/pages` (one per route). Long lists use cursor pagination + an `IntersectionObserver` sentinel and `content-visibility: auto` so off-screen cards cost nothing. Images use `loading="lazy"`; full-resolution files are only loaded in the lightbox. Nothing autoplays unless the user enables it.

## Performance reference

Synthetic stress set (300,000 messages over 4 years, 10,000 photos, 1,000 voices) on the development container: full import 55 s, database 117 MB, every API endpoint < 30 ms.

## Future modules

* Transcription: add a `transcripts(media_id, text, engine, created_at)` table and an optional local engine (e.g. whisper.cpp); the Sound Museum already separates user titles/notes from imported data.
* App-specific parsers (WeChat, iMessage, Telegram …) — see ADDING_A_PARSER.md.
