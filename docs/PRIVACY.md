# Privacy

This project is built to hold some of the most private data two people have. The rules below are design constraints, not settings.

## What stays where

| data | location | leaves your computer? |
| --- | --- | --- |
| original chat exports, photos, voices, videos | wherever you keep them (suggested: `private-data/`) | never; read in place, never copied or modified |
| imported messages, media index, your favorites/notes/moments/settings | `data/museum.db` | never |
| thumbnails, browser-playable audio copies | `data/cache/` | never |
| avatars you upload | `data/avatars/` (re-encoded, metadata stripped) | never |

`private-data/`, `data/`, `uploads/`, `generated/`, `cache/`, `media-derived/`, `*.db`, `*.sqlite*`, `.env`, `demo-data-stress/`, `node_modules/` and `dist/` are git-ignored so `git add -A` cannot accidentally publish them. The committed `demo-data/` is fictional: procedurally drawn images, tone-based "voices", invented dialogue.

## Network

* The server binds to `127.0.0.1` by default: only this computer can connect.
* The app makes **no outbound network requests**: no analytics, telemetry, crash reporting, CDNs, web fonts, map tiles, or AI APIs. The page's Content-Security-Policy (`default-src 'self'`) blocks third-party requests even if a bug tried.
* Referrers are disabled (`Referrer-Policy: no-referrer`), API responses are `Cache-Control: no-store`, and search engines are told not to index (`noindex`).
* Installing dependencies (`pip`, `npm`) needs the internet once; running the museum does not.

If you choose `serve --host 0.0.0.0` to view on a phone, anyone on the same network can reach the port. Set a PIN first and only do this on a network you trust. Traffic inside your LAN is plain HTTP.

## The PIN lock — and its limits

* Stored as a salted PBKDF2-SHA256 hash (240,000 iterations), never in plain text.
* Unlocking gives the browser a random, HttpOnly, SameSite=Strict session cookie held only in server memory; every API call and every media file requires it. Restarting the server locks all browsers.
* Optional auto-lock after inactivity (client-side timer and server-side session expiry). Five wrong attempts cause a 30-second lockout.

**It is not encryption.** Anyone who can read files on your computer can open `data/museum.db` with any SQLite tool and view your original media folders directly. For protection at rest use full-disk encryption (Windows BitLocker / Device Encryption, macOS FileVault, Linux LUKS) and a login password on your computer. The code keeps database and media access in a few places so encrypted storage (e.g. SQLCipher) can be added later.

## Things the software deliberately does not do

* It does not send data anywhere.
* It does not generate captions, summaries, "relationship insights" or emotional labels. Excerpts are real messages chosen by length/spread; titles and notes are only what you write.
* It does not present a guessed photo↔message link as fact: uncertain matches are labelled, and low-confidence guesses are only suggestions in the Review screen.
* It does not delete your original files. `purge` removes only what the app generated.

## Deleting everything

```bash
python -m memory_museum purge          # database, staging db, thumbnails, converted audio, avatars
```

Then delete the `data/` folder (and `private-data/` if you used it) yourself if you want no trace at all. Browser history/cache for `127.0.0.1:8765` can be cleared in your browser.

## Sharing the repository

The repository is safe to make public as long as you only commit what `git status` shows after these ignore rules. Before pushing, check:

```bash
git status --ignored     # your data should appear under "Ignored files"
```
