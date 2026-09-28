# Adding a parser

A parser adapts one export format to the common `ParsedMessage` model. Everything downstream (deduplication, media linking, timeline, stats) works unchanged.

## 1. Write the adapter

Create `memory_museum/parsers/my_app.py`. Example: an export where each line is `YYYYMMDD HHMMSS|sender|kind|payload`.

```python
from __future__ import annotations

from pathlib import Path
from typing import Iterator

from memory_museum.parsers.base import (
    ChatParser, ImportReport, ParsedMessage, detect_encoding, normalize_type, type_from_media_ref,
)
from memory_museum.timeutil import TimestampError, parse_timestamp


class MyAppParser(ChatParser):
    name = "myapp"                      # used by --parser myapp
    description = "MyApp pipe-separated export"
    extensions = (".txt",)

    def sniff(self, path: Path, head: str) -> float:
        # 0..1 confidence; the generic txt parser answers 0.9 for its own layouts,
        # so answer higher only when you are sure it's yours.
        first = head.splitlines()[0] if head else ""
        return 0.95 if first.count("|") == 3 and first[:8].isdigit() else 0.0

    def parse(self, path: Path, report: ImportReport, *, tz=None) -> Iterator[ParsedMessage]:
        try:
            fh = path.open("r", encoding=detect_encoding(path), errors="replace")
        except OSError as e:
            report.issue("unreadable_file", path, None, str(e))
            return
        with fh:
            for lineno, line in enumerate(fh, 1):
                line = line.rstrip("\r\n")
                if not line:
                    continue
                report.records_seen += 1                      # count every record you look at
                parts = line.split("|", 3)
                if len(parts) != 4:
                    report.issue("malformed", path, f"line {lineno}", line[:80])
                    continue                                  # never raise for one bad record
                raw_ts, sender, kind, payload = parts
                try:
                    ts = parse_timestamp(f"{raw_ts[:4]}-{raw_ts[4:6]}-{raw_ts[6:8]} {raw_ts[9:11]}:{raw_ts[11:13]}:{raw_ts[13:15]}", tz)
                except TimestampError as e:
                    report.issue("bad_timestamp", path, f"line {lineno}", f"{e}; kept without a date")
                    ts = None                                 # keep the message, just undated
                msg_type = normalize_type(kind)
                media = payload if msg_type in ("image", "voice", "audio", "video", "file") else None
                if msg_type is None:
                    report.issue("unknown_type", path, f"line {lineno}", f"unknown type {kind!r}")
                    msg_type = type_from_media_ref(payload) or "unknown"
                yield ParsedMessage(
                    sender_id=sender,
                    sender_display_name=sender,
                    timestamp=ts,
                    message_type=msg_type,
                    text=None if media else payload,
                    media_reference=media,
                    source_file=str(path),
                    metadata={"line": lineno, "raw_type": kind} if msg_type == "unknown" else {"line": lineno},
                )
```

Rules of thumb:

* **Never raise** for a bad record — call `report.issue(kind, file, where, detail)` and continue. Issue kinds: `malformed`, `missing_timestamp`, `bad_timestamp`, `unknown_type`, `missing_sender`, `unreadable_file`, `unsupported_file`.
* **Don't drop data**: keep undated messages (`timestamp=None`), map unknown types to `"unknown"`, put extra fields into `metadata`.
* **Stream**: yield messages as you read; don't load huge files into memory when you can avoid it.
* Set `source_message_id` whenever the export has stable ids — it makes re-imports and overlapping exports deduplicate exactly.
* Use `parse_timestamp(value, tz)` so timezone handling stays consistent; convert only what is unambiguous.
* If the format stores dict-like records, `memory_museum.parsers.records.record_to_message()` already handles all the common field aliases.

## 2. Register it

In `memory_museum/parsers/__init__.py`:

```python
from memory_museum.parsers.my_app import MyAppParser

PARSERS: list[ChatParser] = [
    MyAppParser(),          # specific parsers first
    GenericJSONParser(),
    GenericCSVParser(),
    GenericTXTParser(),
]
```

`python -m memory_museum parsers` should now list it.

## 3. Test it with synthetic data only

Add `tests/test_my_app_parser.py` with a few hand-written lines (never real chats), including broken ones:

```python
from memory_museum.parsers import ImportReport, get_parser


def test_myapp(tmp_path):
    p = tmp_path / "x.txt"
    p.write_text("20240301 210315|A|text|hello\nbroken line\n20240301 210400|B|image|IMG_1.jpg\n", encoding="utf-8")
    rep = ImportReport()
    msgs = list(get_parser("myapp").parse(p, rep))
    assert [m.message_type for m in msgs] == ["text", "image"]
    assert rep.issue_counts == {"malformed": 1}
```

Run `python -m pytest`, then try a dry run: `python -m memory_museum import --chat your-export --parser myapp --dry-run`.
