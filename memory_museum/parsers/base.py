"""Parser adapter base classes.

A parser turns one export file into a stream of :class:`ParsedMessage`
objects in the common normalized schema. Parsers must never raise on bad
records: they record an issue on the :class:`ImportReport` and move on.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, Mapping

MESSAGE_TYPES = (
    "text",
    "image",
    "voice",
    "audio",
    "video",
    "sticker",
    "file",
    "link",
    "system",
    "unknown",
)

MEDIA_MESSAGE_TYPES = ("image", "voice", "audio", "video")

_TYPE_ALIASES = {
    "text": "text", "txt": "text", "message": "text", "msg": "text", "文本": "text", "文字": "text", "1": "text",
    "image": "image", "img": "image", "photo": "image", "picture": "image", "pic": "image", "图片": "image",
    "照片": "image", "3": "image",
    "voice": "voice", "ptt": "voice", "voice_note": "voice", "voicenote": "voice", "语音": "voice", "34": "voice",
    "audio": "audio", "music": "audio", "音频": "audio", "音乐": "audio",
    "video": "video", "视频": "video", "小视频": "video", "43": "video",
    "sticker": "sticker", "emoji": "sticker", "emoticon": "sticker", "gif": "sticker", "表情": "sticker",
    "动画表情": "sticker", "47": "sticker",
    "file": "file", "document": "file", "attachment": "file", "文件": "file",
    "link": "link", "url": "link", "share": "link", "链接": "link", "分享": "link", "49": "link",
    "system": "system", "notice": "system", "recall": "system", "revoke": "system", "系统": "system",
    "系统消息": "system", "撤回": "system", "10000": "system",
}

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".heif", ".bmp"}
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".amr", ".ogg", ".opus", ".flac", ".wma", ".silk", ".caf"}
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".3gp", ".webm", ".mkv", ".avi"}


def normalize_type(raw: Any) -> str | None:
    """Map an export's type label to a known type; None if unrecognised."""
    if raw is None:
        return None
    key = str(raw).strip().lower()
    if not key:
        return None
    return _TYPE_ALIASES.get(key)


def type_from_media_ref(ref: str | None) -> str | None:
    if not ref:
        return None
    ext = Path(ref.split("?")[0]).suffix.lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in VIDEO_EXTS:
        return "video"
    if ext in AUDIO_EXTS:
        return "voice"
    return "file" if ext else None


# Inline markers commonly found in text exports, e.g. "[图片] IMG_0001.jpg"
_MARKER = re.compile(
    r"^\s*[\[【<](图片|照片|语音|视频|表情|动画表情|文件|链接|音频|Photo|Image|Picture|Voice|Audio|Video|Sticker|File|Link)"
    r"[\]】>]\s*(.*)$",
    re.IGNORECASE,
)
_DURATION_ONLY = re.compile(r"^\d+(?:\.\d+)?\s*(?:\"|″|”|''|秒|s|sec)?$", re.IGNORECASE)
_OMITTED = re.compile(r"^\s*<(Media|image|video|audio|sticker) omitted>\s*$", re.IGNORECASE)
_MEDIA_FILENAME = re.compile(r"([\w\-. ()]+\.(?:jpe?g|png|webp|gif|heic|mp3|wav|m4a|aac|amr|mp4|mov|3gp|ogg|opus))",
                             re.IGNORECASE)


def split_marker(text: str) -> tuple[str | None, str | None, str]:
    """Detect a media marker in text. Returns (type, media_ref, remaining_text)."""
    m = _MARKER.match(text)
    if m:
        msg_type = normalize_type(m.group(1)) or "unknown"
        rest = m.group(2).strip()
        fm = _MEDIA_FILENAME.search(rest)
        ref = fm.group(1).strip() if fm else None
        remaining = rest.replace(fm.group(1), "").strip() if fm else rest
        if _DURATION_ONLY.match(remaining):  # e.g. [语音] voice.m4a 8"
            remaining = ""
        return msg_type, ref, remaining
    m = _OMITTED.match(text)
    if m:
        kind = m.group(1).lower()
        return ("image" if kind == "media" else normalize_type(kind) or "unknown"), None, ""
    return None, None, text


@dataclass
class ParsedMessage:
    sender_id: str | None
    sender_display_name: str | None
    timestamp: datetime | None
    message_type: str
    text: str | None = None
    conversation_id: str = "main"
    reply_to_message_id: str | None = None
    media_reference: str | None = None
    source_file: str | None = None
    source_message_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


ISSUE_KINDS = (
    "malformed",
    "missing_timestamp",
    "bad_timestamp",
    "unknown_type",
    "missing_sender",
    "unreadable_file",
    "unsupported_file",
)


@dataclass
class ImportReport:
    """Accumulates counts and a bounded list of detailed issues."""

    files: list[str] = field(default_factory=list)
    records_seen: int = 0
    imported: int = 0
    duplicates: int = 0
    by_type: Counter = field(default_factory=Counter)
    issue_counts: Counter = field(default_factory=Counter)
    issues: list[dict[str, Any]] = field(default_factory=list)
    participants: Counter = field(default_factory=Counter)
    first_ts: str | None = None
    last_ts: str | None = None
    max_issue_details: int = 200

    def issue(self, kind: str, source: str | Path | None, where: Any, detail: str) -> None:
        self.issue_counts[kind] += 1
        if len(self.issues) < self.max_issue_details:
            self.issues.append(
                {"kind": kind, "file": str(source) if source else None, "where": where, "detail": detail[:300]}
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "files": self.files,
            "records_seen": self.records_seen,
            "imported": self.imported,
            "duplicates": self.duplicates,
            "by_type": dict(self.by_type),
            "issue_counts": dict(self.issue_counts),
            "issues": self.issues,
            "participants": dict(self.participants),
            "first_ts": self.first_ts,
            "last_ts": self.last_ts,
        }


class ChatParser(ABC):
    """Base class for chat export adapters."""

    #: short identifier used on the command line (``--parser name``)
    name: str = ""
    #: human description shown by ``memory_museum parsers``
    description: str = ""
    #: file extensions this parser may handle
    extensions: tuple[str, ...] = ()

    def sniff(self, path: Path, head: str) -> float:
        """Return confidence 0..1 that this parser understands the file.

        ``head`` is the first few KB of the file decoded as text.
        """
        return 0.5 if path.suffix.lower() in self.extensions else 0.0

    @abstractmethod
    def parse(self, path: Path, report: ImportReport, *, tz=None) -> Iterator[ParsedMessage]:
        """Yield normalized messages. Never raise for bad records."""


def first_of(record: Mapping[str, Any], keys: tuple[str, ...]) -> Any:
    for k in keys:
        if k in record and record[k] not in (None, ""):
            return record[k]
    lowered = {str(k).lower(): v for k, v in record.items()}
    for k in keys:
        v = lowered.get(k.lower())
        if v not in (None, ""):
            return v
    return None


TS_KEYS = ("timestamp", "time", "datetime", "date", "ts", "created_at", "createTime", "create_time", "sent_at",
           "时间", "发送时间", "日期")
SENDER_NAME_KEYS = ("sender_name", "sender", "from", "author", "name", "talker", "nickname", "发送者", "发送人",
                    "昵称")
SENDER_ID_KEYS = ("sender_id", "from_id", "user_id", "author_id", "uid", "talker_id", "发送者ID")
TEXT_KEYS = ("text", "content", "message", "body", "msg", "内容", "消息")
TYPE_KEYS = ("type", "msg_type", "message_type", "kind", "类型", "消息类型")
MEDIA_KEYS = ("media", "media_path", "media_file", "file", "filename", "attachment", "path", "photo", "voice",
              "video", "附件", "文件")
ID_KEYS = ("id", "message_id", "msg_id", "msgid", "msgId", "消息ID")
REPLY_KEYS = ("reply_to", "reply_to_id", "reply_to_message_id", "quote_id", "quoted_id", "引用")
CONV_KEYS = ("conversation_id", "chat_id", "conversation", "chat", "会话")


def read_text_head(path: Path, size: int = 4096) -> str:
    try:
        raw = path.open("rb").read(size)
    except OSError:
        return ""
    for enc in ("utf-8-sig", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def detect_encoding(path: Path) -> str:
    """UTF-8 (with/without BOM) first, then GB18030 for Chinese Windows exports."""
    try:
        with path.open("rb") as fh:
            chunk = fh.read(1 << 20)
    except OSError:
        return "utf-8-sig"
    try:
        chunk.decode("utf-8-sig")
        return "utf-8-sig"
    except UnicodeDecodeError as e:
        # a multi-byte char cut at the chunk boundary is still UTF-8
        if e.start >= len(chunk) - 4:
            return "utf-8-sig"
    try:
        chunk.decode("gb18030")
        return "gb18030"
    except UnicodeDecodeError:
        return "utf-8-sig"
