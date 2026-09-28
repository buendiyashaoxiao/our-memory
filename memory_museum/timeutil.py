"""Timestamp parsing.

All timestamps are stored as naive *local wall-clock* ISO strings
(``YYYY-MM-DDTHH:MM:SS``). Chat exports almost always record local time, and
"which day did this happen" is what the museum cares about.

* Naive inputs are assumed to already be local time.
* Timezone-aware inputs (``...Z``, ``+08:00``, epoch numbers) are converted to
  the configured local timezone, then made naive.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone, tzinfo

TS_FORMAT = "%Y-%m-%dT%H:%M:%S"

_EPOCH_MIN = 946684800  # 2000-01-01
_EPOCH_MAX = 4102444800  # 2100-01-01

_CN_DATETIME = re.compile(
    r"^\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?"
    r"(?:\s*(上午|下午|凌晨|早上|中午|晚上)?\s*(\d{1,2})[:：点时](\d{1,2})?(?:[:：分](\d{1,2}))?秒?)?\s*$"
)
_YMD_DATETIME = re.compile(
    r"^\s*(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})"
    r"(?:[ T,]+(\d{1,2}):(\d{1,2})(?::(\d{1,2})(?:[.,](\d{1,6}))?)?\s*([AaPp][Mm])?)?"
    r"\s*(Z|[+-]\d{2}:?\d{2})?\s*$"
)
_DMY_OR_MDY = re.compile(
    r"^\s*(\d{1,2})[/.](\d{1,2})[/.](\d{2,4}),?"
    r"(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?\s*([AaPp][Mm])?)?\s*$"
)


class TimestampError(ValueError):
    pass


def _local_tz(tz: tzinfo | None) -> tzinfo:
    if tz is not None:
        return tz
    return datetime.now().astimezone().tzinfo or timezone.utc


def get_tz(name: str | None) -> tzinfo | None:
    """Return a tzinfo for an IANA name; None means 'this computer's local time'."""
    if not name or name == "local":
        return None
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(name)
    except Exception:  # missing tzdata on Windows, typo, ...
        m = re.fullmatch(r"(?:UTC)?([+-])(\d{1,2})(?::?(\d{2}))?", name.strip())
        if m:
            sign = 1 if m.group(1) == "+" else -1
            delta = timedelta(hours=int(m.group(2)), minutes=int(m.group(3) or 0))
            return timezone(sign * delta)
        return None


def _apply_ampm(hour: int, marker: str | None) -> int:
    if not marker:
        return hour
    m = marker.lower()
    if m in ("pm", "下午", "晚上") and hour < 12:
        return hour + 12
    if m in ("am", "凌晨", "上午", "早上") and hour == 12:
        return 0
    if m == "中午" and hour < 11:
        return hour + 12
    return hour


def _from_epoch(value: float, tz: tzinfo | None) -> datetime:
    if value > 1e17:  # nanoseconds
        value = value / 1e9
    elif value > 1e14:  # microseconds
        value = value / 1e6
    elif value > 1e11:  # milliseconds
        value = value / 1000
    if not (_EPOCH_MIN <= value <= _EPOCH_MAX):
        raise TimestampError(f"epoch value out of range: {value}")
    return datetime.fromtimestamp(value, tz=timezone.utc).astimezone(_local_tz(tz)).replace(tzinfo=None)


def parse_timestamp(value, tz: tzinfo | None = None, *, day_first: bool | None = None) -> datetime:
    """Parse many common chat-export timestamp formats into a naive local datetime.

    Raises TimestampError when the value cannot be parsed confidently.
    ``day_first`` resolves ``03/04/2024``-style dates; when None, ambiguous
    values (both parts <= 12) are rejected rather than guessed.
    """
    if value is None:
        raise TimestampError("missing timestamp")
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(_local_tz(tz)).replace(tzinfo=None)
        return value
    if isinstance(value, bool):
        raise TimestampError("boolean is not a timestamp")
    if isinstance(value, (int, float)):
        return _from_epoch(float(value), tz)

    s = str(value).strip()
    if not s:
        raise TimestampError("empty timestamp")
    if re.fullmatch(r"\d{9,17}(\.\d+)?", s):
        return _from_epoch(float(s), tz)

    m = _YMD_DATETIME.match(s)
    if m:
        y, mo, d, hh, mm, ss, frac, ampm, off = m.groups()
        try:
            hour = _apply_ampm(int(hh or 0), ampm)
            dt = datetime(int(y), int(mo), int(d), hour, int(mm or 0), int(ss or 0))
        except ValueError as e:
            raise TimestampError(str(e)) from e
        if off:
            if off == "Z":
                offset = timezone.utc
            else:
                sign = 1 if off[0] == "+" else -1
                digits = off[1:].replace(":", "")
                offset = timezone(sign * timedelta(hours=int(digits[:2]), minutes=int(digits[2:])))
            dt = dt.replace(tzinfo=offset).astimezone(_local_tz(tz)).replace(tzinfo=None)
        return dt

    m = _CN_DATETIME.match(s)
    if m:
        y, mo, d, marker, hh, mm, ss = m.groups()
        try:
            hour = _apply_ampm(int(hh or 0), marker)
            return datetime(int(y), int(mo), int(d), hour, int(mm or 0), int(ss or 0))
        except ValueError as e:
            raise TimestampError(str(e)) from e

    m = _DMY_OR_MDY.match(s)
    if m:
        a, b, y, hh, mm, ss, ampm = m.groups()
        a_i, b_i, y_i = int(a), int(b), int(y)
        if y_i < 100:
            y_i += 2000
        if day_first is None:
            if a_i > 12 >= b_i:
                day_first = True
            elif b_i > 12 >= a_i:
                day_first = False
            else:
                raise TimestampError(f"ambiguous day/month order: {s}")
        day_, month_ = (a_i, b_i) if day_first else (b_i, a_i)
        try:
            hour = _apply_ampm(int(hh or 0), ampm)
            return datetime(y_i, month_, day_, hour, int(mm or 0), int(ss or 0))
        except ValueError as e:
            raise TimestampError(str(e)) from e

    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        raise TimestampError(f"unrecognised timestamp: {s[:40]}") from None
    if dt.tzinfo is not None:
        dt = dt.astimezone(_local_tz(tz)).replace(tzinfo=None)
    return dt


def fmt(dt: datetime | None) -> str | None:
    return dt.strftime(TS_FORMAT) if dt else None


def day_of(ts: str | None) -> str | None:
    return ts[:10] if ts else None


def parse_day(s: str) -> date:
    return date.fromisoformat(s)


_FILENAME_TS = [
    # IMG_20230417_203015, VID_20230417_203015, PXL_20230417_203015123, 20230417_203015
    re.compile(r"(?<!\d)(20\d{2})(\d{2})(\d{2})[_\-T ]?(\d{2})(\d{2})(\d{2})(?:\d{3})?(?!\d)"),
    # 2023-04-17 20.30.15, 2023-04-17_20-30-15, Screenshot 2023-04-17 at 20.30.15
    re.compile(r"(20\d{2})-(\d{2})-(\d{2})[ _T](?:at )?(\d{2})[.\-:](\d{2})[.\-:](\d{2})"),
    # WhatsApp: IMG-20230417-WA0001 (date only)
    re.compile(r"(?<!\d)(20\d{2})(\d{2})(\d{2})-WA\d+"),
    # mmexport1681734615000 style epoch millis
    re.compile(r"(?:mmexport|wx_camera_|microMsg\.)(\d{13})"),
]


def timestamp_from_filename(name: str) -> tuple[datetime, bool] | None:
    """Best-effort capture time from common phone camera / messenger filenames.

    Returns ``(datetime, precise)``; ``precise`` is False when the filename only
    carries a date (the time is then set to noon as a placeholder).
    """
    for i, pattern in enumerate(_FILENAME_TS):
        m = pattern.search(name)
        if not m:
            continue
        try:
            if i == 3:
                return _from_epoch(int(m.group(1)), None), True
            parts = [int(g) for g in m.groups()]
            precise = len(parts) == 6
            if not precise:
                parts += [12, 0, 0]
            dt = datetime(*parts)
        except (ValueError, TimestampError):
            continue
        if 2000 <= dt.year <= 2100:
            return dt, precise
    return None
