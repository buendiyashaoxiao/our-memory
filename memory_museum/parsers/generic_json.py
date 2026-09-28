"""Generic JSON / JSON Lines chat export.

Accepted shapes::

    [ {message}, {message}, ... ]
    { "messages": [...], "participants": [{"id": "a", "name": "A"}], "conversation_id": "x" }
    one JSON object per line (.jsonl / .ndjson) — recommended for very large archives
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

from memory_museum.parsers.base import ChatParser, ImportReport, ParsedMessage, detect_encoding
from memory_museum.parsers.records import record_to_message


def _participants_map(raw: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    if isinstance(raw, list):
        for p in raw:
            if isinstance(p, dict):
                pid = p.get("id") or p.get("sender_id") or p.get("name")
                name = p.get("name") or p.get("display_name") or pid
                if pid:
                    out[str(pid)] = str(name)
    elif isinstance(raw, dict):
        for k, v in raw.items():
            out[str(k)] = str(v.get("name") if isinstance(v, dict) else v)
    return out


class GenericJSONParser(ChatParser):
    name = "json"
    description = "JSON array, {messages: [...]} object, or JSON Lines (one message object per line)"
    extensions = (".json", ".jsonl", ".ndjson")

    def sniff(self, path: Path, head: str) -> float:
        if path.suffix.lower() not in self.extensions:
            return 0.0
        stripped = head.lstrip()
        return 0.9 if stripped[:1] in ("[", "{") else 0.1

    def parse(self, path: Path, report: ImportReport, *, tz=None) -> Iterator[ParsedMessage]:
        enc = detect_encoding(path)
        if path.suffix.lower() in (".jsonl", ".ndjson"):
            yield from self._parse_lines(path, enc, report, tz)
            return
        try:
            with path.open("r", encoding=enc, errors="replace") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as e:
            # A truncated/corrupt .json may still be line-delimited; try that before giving up.
            report.issue("unreadable_file", path, None, f"could not parse as a JSON document ({e}); trying line mode")
            yield from self._parse_lines(path, enc, report, tz)
            return

        participants: dict[str, str] = {}
        conv = "main"
        records: Any = data
        if isinstance(data, dict):
            participants = _participants_map(data.get("participants") or data.get("members"))
            conv = str(data.get("conversation_id") or data.get("chat_id") or "main")
            records = data.get("messages") or data.get("data") or data.get("records")
        if not isinstance(records, list):
            report.issue("malformed", path, None, "no list of messages found in JSON document")
            return
        for i, rec in enumerate(records):
            report.records_seen += 1
            msg = record_to_message(rec, source=path, where=f"index {i}", report=report, tz=tz,
                                    default_conversation=conv, participants=participants)
            if msg:
                yield msg

    def _parse_lines(self, path: Path, enc: str, report: ImportReport, tz) -> Iterator[ParsedMessage]:
        try:
            fh = path.open("r", encoding=enc, errors="replace")
        except OSError as e:
            report.issue("unreadable_file", path, None, str(e))
            return
        with fh:
            for lineno, line in enumerate(fh, 1):
                line = line.strip().rstrip(",")
                if not line or line in ("[", "]", "{", "}"):
                    continue
                report.records_seen += 1
                try:
                    rec = json.loads(line)
                except ValueError:
                    report.issue("malformed", path, f"line {lineno}", f"invalid JSON: {line[:80]}")
                    continue
                msg = record_to_message(rec, source=path, where=f"line {lineno}", report=report, tz=tz)
                if msg:
                    yield msg
