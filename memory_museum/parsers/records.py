"""Shared normalization for dict-shaped records (JSON objects, CSV rows)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from memory_museum.parsers.base import (
    CONV_KEYS,
    ID_KEYS,
    MEDIA_KEYS,
    REPLY_KEYS,
    SENDER_ID_KEYS,
    SENDER_NAME_KEYS,
    TEXT_KEYS,
    TS_KEYS,
    TYPE_KEYS,
    ImportReport,
    ParsedMessage,
    first_of,
    normalize_type,
    split_marker,
    type_from_media_ref,
)
from memory_museum.timeutil import TimestampError, parse_timestamp

_KNOWN_KEYS = {k.lower() for k in TS_KEYS + SENDER_NAME_KEYS + SENDER_ID_KEYS + TEXT_KEYS + TYPE_KEYS + MEDIA_KEYS
               + ID_KEYS + REPLY_KEYS + CONV_KEYS} | {"attachments", "duration"}


def _media_ref(record: Mapping[str, Any]) -> str | None:
    ref = first_of(record, MEDIA_KEYS)
    if ref is None:
        atts = first_of(record, ("attachments", "media_files", "files"))
        if isinstance(atts, list) and atts:
            ref = atts[0]
    if isinstance(ref, Mapping):
        ref = first_of(ref, ("filename", "file", "path", "name", "uri", "url"))
    if ref is None:
        return None
    ref = str(ref).strip()
    return ref or None


def record_to_message(
    record: Mapping[str, Any],
    *,
    source: Path,
    where: Any,
    report: ImportReport,
    tz=None,
    default_conversation: str = "main",
    participants: Mapping[str, str] | None = None,
) -> ParsedMessage | None:
    if not isinstance(record, Mapping):
        report.issue("malformed", source, where, f"expected an object, got {type(record).__name__}")
        return None

    raw_ts = first_of(record, TS_KEYS)
    ts = None
    if raw_ts is None:
        report.issue("missing_timestamp", source, where, "record has no timestamp; kept without a date")
    else:
        try:
            ts = parse_timestamp(raw_ts, tz)
        except TimestampError as e:
            report.issue("bad_timestamp", source, where, f"{e}; kept without a date")

    sender_id = first_of(record, SENDER_ID_KEYS)
    sender_name = first_of(record, SENDER_NAME_KEYS)
    if isinstance(sender_name, Mapping):
        sender_id = sender_id or first_of(sender_name, ("id", "uid"))
        sender_name = first_of(sender_name, ("name", "display_name", "nickname"))
    sender_id = str(sender_id).strip() if sender_id is not None else None
    sender_name = str(sender_name).strip() if sender_name is not None else None
    if not sender_id and sender_name:
        sender_id = sender_name
    if sender_id and not sender_name and participants:
        sender_name = participants.get(sender_id)

    text = first_of(record, TEXT_KEYS)
    if text is not None and not isinstance(text, str):
        text = str(text)
    media_ref = _media_ref(record)

    raw_type = first_of(record, TYPE_KEYS)
    msg_type = normalize_type(raw_type)
    marker_type = None
    if text:
        marker_type, marker_ref, rest = split_marker(text)
        if marker_type:
            media_ref = media_ref or marker_ref
            text = rest or None
    if msg_type is None:
        if raw_type is not None:
            report.issue("unknown_type", source, where, f"unknown message type {raw_type!r}; kept as 'unknown'")
            msg_type = "unknown"
        else:
            msg_type = marker_type or type_from_media_ref(media_ref) or "text"

    if not sender_id and msg_type != "system":
        report.issue("missing_sender", source, where, "record has no sender")

    if msg_type == "text" and not text and not media_ref:
        report.issue("malformed", source, where, "empty text message")
        return None

    source_id = first_of(record, ID_KEYS)
    reply_to = first_of(record, REPLY_KEYS)
    conv = first_of(record, CONV_KEYS)
    metadata = {k: v for k, v in record.items() if str(k).lower() not in _KNOWN_KEYS and v not in (None, "")}
    if raw_type is not None and normalize_type(raw_type) is None:
        metadata["raw_type"] = raw_type
    duration = first_of(record, ("duration", "voice_length", "时长"))
    if duration is not None:
        metadata["duration"] = duration
    if ts is None and raw_ts is not None:
        metadata["raw_timestamp"] = str(raw_ts)[:100]

    return ParsedMessage(
        conversation_id=str(conv) if conv else default_conversation,
        sender_id=sender_id,
        sender_display_name=sender_name,
        timestamp=ts,
        message_type=msg_type,
        text=text,
        reply_to_message_id=str(reply_to) if reply_to is not None else None,
        media_reference=media_ref,
        source_file=str(source),
        source_message_id=str(source_id) if source_id is not None else None,
        metadata=metadata,
    )
