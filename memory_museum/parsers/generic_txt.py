"""Generic plain-text chat logs.

Recognised line layouts (mixed freely within one file)::

    2024-03-01 21:03:15 林夏: 到家了吗
    [2024-03-01 21:03] 林夏：到家了吗
    2024-03-01 21:03:15 林夏            <- block header; following lines are the message
    到家了吗
    ———— 2024-03-01 ————                <- date line; later lines may carry only a time
    21:03 林夏: 到家了吗
    01/03/2024, 21:03 - 林夏: 到家了吗    <- WhatsApp-style (day/month order auto-detected)

Media markers such as ``[图片] IMG_0001.jpg`` or ``<Media omitted>`` become
typed messages. Lines that continue a message are appended to it.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator

from memory_museum.parsers.base import ChatParser, ImportReport, ParsedMessage, detect_encoding, split_marker
from memory_museum.timeutil import TimestampError, parse_timestamp

_DATE = r"\d{4}\s*[-/.年]\s*\d{1,2}\s*[-/.月]\s*\d{1,2}\s*日?"
_TIME = r"(?:上午|下午|凌晨|晚上|中午|早上)?\s*\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AaPp][Mm])?"
_SENDER = r"(?P<sender>[^:：\[\]\n]{1,40}?)"

INLINE = re.compile(rf"^\[?(?P<date>{_DATE})[ T,]+(?P<time>{_TIME})\]?\s*[-–]?\s*{_SENDER}\s*[:：]\s?(?P<text>.*)$")
BLOCK = re.compile(rf"^\[?(?P<date>{_DATE})[ T,]+(?P<time>{_TIME})\]?\s+(?P<sender>[^:：\n]{{1,40}}?)\s*$")
WHATSAPP = re.compile(
    rf"^\[?(?P<date>\d{{1,2}}/\d{{1,2}}/\d{{2,4}}),?\s+(?P<time>{_TIME})\]?\s*(?:-\s*)?"
    rf"(?:(?P<sender>[^:]{{1,40}}?):\s)?(?P<text>.*)$"
)
TIME_ONLY = re.compile(rf"^\[?(?P<time>{_TIME})\]?\s+{_SENDER}\s*[:：]\s?(?P<text>.*)$")
DATE_LINE = re.compile(rf"^[\s—\-=*#]*(?P<date>{_DATE})(?:\s*(?:星期|周)[一二三四五六日天])?[\s—\-=*#]*$")


def _norm_date(d: str) -> str:
    return re.sub(r"\s+", "", d).replace("年", "-").replace("月", "-").replace("日", "").replace("/", "-").replace(".", "-")


class GenericTXTParser(ChatParser):
    name = "txt"
    description = "Plain-text logs: 'YYYY-MM-DD HH:MM[:SS] Name: text', block style, date-line + time style, WhatsApp style"
    extensions = (".txt", ".log")

    def sniff(self, path: Path, head: str) -> float:
        if path.suffix.lower() not in self.extensions:
            return 0.0
        lines = [ln for ln in head.splitlines()[:30] if ln.strip()]
        hits = sum(1 for ln in lines if INLINE.match(ln) or BLOCK.match(ln) or WHATSAPP.match(ln) or DATE_LINE.match(ln))
        return 0.9 if hits else 0.2

    def _day_first(self, path: Path, enc: str) -> bool | None:
        first_big = second_big = False
        try:
            with path.open("r", encoding=enc, errors="replace") as fh:
                for line in fh:
                    m = WHATSAPP.match(line)
                    if not m:
                        continue
                    a, b, _ = m.group("date").split("/")
                    first_big |= int(a) > 12
                    second_big |= int(b) > 12
        except OSError:
            return None
        if first_big and not second_big:
            return True
        if second_big and not first_big:
            return False
        return None

    def parse(self, path: Path, report: ImportReport, *, tz=None) -> Iterator[ParsedMessage]:
        enc = detect_encoding(path)
        day_first = None
        try:
            fh = path.open("r", encoding=enc, errors="replace")
        except OSError as e:
            report.issue("unreadable_file", path, None, str(e))
            return

        pending: dict | None = None
        current_date: str | None = None
        checked_whatsapp = False

        def flush(p: dict | None) -> ParsedMessage | None:
            if p is None:
                return None
            report.records_seen += 1
            text = "\n".join(p["lines"]).strip()
            ts = None
            try:
                ts = parse_timestamp(p["raw_ts"], tz, day_first=p.get("day_first"))
            except TimestampError as e:
                report.issue("bad_timestamp", path, f"line {p['lineno']}", f"{e}; kept without a date")
            msg_type = p.get("type") or "text"
            media_ref = None
            if msg_type == "text":
                marker, media_ref, rest = split_marker(text)
                if marker:
                    msg_type, text = marker, rest
            if msg_type == "text" and not text:
                report.issue("malformed", path, f"line {p['lineno']}", "message header without any text")
                return None
            sender = (p.get("sender") or "").strip() or None
            meta = {"line": p["lineno"]}
            if ts is None:
                meta["raw_timestamp"] = p["raw_ts"]
            return ParsedMessage(
                sender_id=sender,
                sender_display_name=sender,
                timestamp=ts,
                message_type=msg_type,
                text=text or None,
                media_reference=media_ref,
                source_file=str(path),
                metadata=meta,
            )

        with fh:
            for lineno, raw in enumerate(fh, 1):
                line = raw.rstrip("\r\n")
                if not line.strip():
                    if pending and pending["lines"]:
                        pending["lines"].append("")
                    continue

                m = INLINE.match(line)
                if m:
                    msg = flush(pending)
                    if msg:
                        yield msg
                    current_date = _norm_date(m.group("date"))
                    pending = {"raw_ts": f"{current_date} {m.group('time')}", "sender": m.group("sender"),
                               "lines": [m.group("text")], "lineno": lineno}
                    continue

                m = BLOCK.match(line)
                if m:
                    msg = flush(pending)
                    if msg:
                        yield msg
                    current_date = _norm_date(m.group("date"))
                    pending = {"raw_ts": f"{current_date} {m.group('time')}", "sender": m.group("sender"),
                               "lines": [], "lineno": lineno}
                    continue

                m = WHATSAPP.match(line)
                if m:
                    if not checked_whatsapp:
                        day_first = self._day_first(path, enc)
                        checked_whatsapp = True
                    msg = flush(pending)
                    if msg:
                        yield msg
                    pending = {"raw_ts": f"{m.group('date')} {m.group('time')}", "sender": m.group("sender"),
                               "lines": [m.group("text")], "lineno": lineno, "day_first": day_first,
                               "type": None if m.group("sender") else "system"}
                    continue

                m = DATE_LINE.match(line)
                if m:
                    msg = flush(pending)
                    if msg:
                        yield msg
                    pending = None
                    current_date = _norm_date(m.group("date"))
                    continue

                m = TIME_ONLY.match(line)
                if m and current_date:
                    msg = flush(pending)
                    if msg:
                        yield msg
                    pending = {"raw_ts": f"{current_date} {m.group('time')}", "sender": m.group("sender"),
                               "lines": [m.group("text")], "lineno": lineno}
                    continue

                if pending is not None:
                    pending["lines"].append(line)
                else:
                    report.records_seen += 1
                    report.issue("malformed", path, f"line {lineno}", f"unrecognised line: {line[:80]}")

            msg = flush(pending)
            if msg:
                yield msg
