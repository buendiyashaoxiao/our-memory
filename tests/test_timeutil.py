from datetime import datetime, timedelta, timezone

import pytest

from memory_museum.timeutil import TimestampError, get_tz, parse_timestamp, timestamp_from_filename

UTC8 = timezone(timedelta(hours=8))


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("2024-03-01 21:03:15", datetime(2024, 3, 1, 21, 3, 15)),
        ("2024/3/1 21:03", datetime(2024, 3, 1, 21, 3)),
        ("2024.03.01", datetime(2024, 3, 1)),
        ("2024-03-01T21:03:15", datetime(2024, 3, 1, 21, 3, 15)),
        ("2024-03-01 09:03 PM", datetime(2024, 3, 1, 21, 3)),
        ("2024-03-01 12:10 am", datetime(2024, 3, 1, 0, 10)),
        ("2024年3月1日 21:03", datetime(2024, 3, 1, 21, 3)),
        ("2024年3月1日 下午3:05", datetime(2024, 3, 1, 15, 5)),
        ("2024年3月1日", datetime(2024, 3, 1)),
        ("17/04/2023 20:30", datetime(2023, 4, 17, 20, 30)),
        ("4/17/23, 8:30 PM", datetime(2023, 4, 17, 20, 30)),
    ],
)
def test_parse_naive_formats(raw, expected):
    assert parse_timestamp(raw) == expected


def test_timezone_aware_values_convert_to_configured_local_time():
    assert parse_timestamp("2024-03-01T13:00:00Z", UTC8) == datetime(2024, 3, 1, 21, 0)
    assert parse_timestamp("2024-03-01T21:00:00+08:00", UTC8) == datetime(2024, 3, 1, 21, 0)
    assert parse_timestamp("2024-03-01T15:00:00+02:00", UTC8) == datetime(2024, 3, 1, 21, 0)


def test_epoch_seconds_milliseconds_and_strings():
    expected = datetime(2024, 3, 1, 21, 0)
    secs = 1709298000  # 2024-03-01 13:00 UTC
    assert parse_timestamp(secs, UTC8) == expected
    assert parse_timestamp(secs * 1000, UTC8) == expected
    assert parse_timestamp(str(secs), UTC8) == expected


@pytest.mark.parametrize("bad", [None, "", "昨天晚上", "2024-13-40 10:00", 12, True, "03/04/2024"])
def test_unparseable_or_ambiguous_values_raise(bad):
    with pytest.raises(TimestampError):
        parse_timestamp(bad)


def test_ambiguous_day_month_can_be_resolved_explicitly():
    assert parse_timestamp("03/04/2024", day_first=True) == datetime(2024, 4, 3)
    assert parse_timestamp("03/04/2024", day_first=False) == datetime(2024, 3, 4)


def test_get_tz():
    assert get_tz("local") is None
    assert get_tz("UTC+8").utcoffset(None) == timedelta(hours=8)


@pytest.mark.parametrize(
    "name, expected, precise",
    [
        ("IMG_20230417_203015.jpg", datetime(2023, 4, 17, 20, 30, 15), True),
        ("VID_20230417_203015.mp4", datetime(2023, 4, 17, 20, 30, 15), True),
        ("PXL_20230417_203015123.jpg", datetime(2023, 4, 17, 20, 30, 15), True),
        ("Screenshot 2023-04-17 at 20.30.15.png", datetime(2023, 4, 17, 20, 30, 15), True),
        ("IMG-20230417-WA0003.jpg", datetime(2023, 4, 17, 12, 0, 0), False),
    ],
)
def test_timestamp_from_filename(name, expected, precise):
    assert timestamp_from_filename(name) == (expected, precise)


def test_filename_without_timestamp():
    assert timestamp_from_filename("holiday.jpg") is None
    assert timestamp_from_filename("IMG_99999999_999999.jpg") is None
