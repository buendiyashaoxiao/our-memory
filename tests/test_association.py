from datetime import datetime

import pytest

from memory_museum.association import associate, link_manually, reset_manual, score_time_match
from memory_museum.importer import import_chat
from memory_museum.media.scanner import import_media

from .conftest import make_photo, write_json


def media_row(conn, name):
    return conn.execute("SELECT * FROM media WHERE original_filename = ?", (name,)).fetchone()


@pytest.fixture
def imported(conn, paths, small_archive):
    import_chat(conn, [small_archive["chat"]])
    import_media(conn, [small_archive["media"]], paths)
    return associate(conn)


def test_exact_filename_match(conn, imported):
    r = media_row(conn, "IMG_20240301_195930.jpg")
    assert (r["association_confidence"], r["association_method"]) == ("exact", "exact_filename")
    msg = conn.execute("SELECT source_message_id FROM messages WHERE id = ?", (r["message_id"],)).fetchone()[0]
    assert msg == "3"
    assert media_row(conn, "voice_1.wav")["association_confidence"] == "exact"


def test_fuzzy_match_by_time_is_high_confidence_when_close_and_unique(conn, imported):
    r = media_row(conn, "IMG_20240302_205950.jpg")  # 10 s before the "[图片]" message
    assert r["association_confidence"] == "high"
    assert r["association_method"] == "time_proximity"


def test_unrelated_media_stays_unassociated(conn, imported):
    r = media_row(conn, "IMG_20240304_100000.jpg")
    assert r["message_id"] is None and r["suggested_message_id"] is None


def test_missing_reference_is_reported(imported):
    assert imported.unresolved_refs == 1
    assert "missing.jpg" in imported.unresolved_examples


@pytest.mark.parametrize(
    "delta, source, runner_up, expected",
    [
        (30, "exif", None, "high"),
        (30, "exif", 45, "medium"),  # another candidate almost as close -> less sure
        (300, "exif", None, "medium"),
        (300, "mtime", None, "low"),  # unreliable clock -> downgrade
        (1200, "exif", None, "low"),
        (5000, "exif", None, None),
    ],
)
def test_confidence_scoring(delta, source, runner_up, expected):
    assert score_time_match(delta, source, runner_up) == expected


def test_low_confidence_is_only_a_suggestion(conn, paths, tmp_path):
    write_json(tmp_path / "c" / "c.json", [{"id": 1, "time": "2024-01-01 12:00:00", "sender": "A", "type": "image"}])
    make_photo(tmp_path / "m" / "p.jpg", datetime(2024, 1, 1, 12, 20))  # 20 minutes apart
    import_chat(conn, [tmp_path / "c"])
    import_media(conn, [tmp_path / "m"], paths)
    rep = associate(conn)
    r = media_row(conn, "p.jpg")
    assert r["message_id"] is None
    assert r["suggested_message_id"] is not None and r["association_confidence"] == "low"
    assert rep.low_suggestions == 1


def test_same_filename_in_two_folders_is_not_exact(conn, paths, tmp_path):
    write_json(tmp_path / "c" / "c.json", [{"id": 1, "time": "2024-01-01 12:00:00", "sender": "A", "media": "x.jpg"}])
    make_photo(tmp_path / "m" / "one" / "x.jpg", datetime(2024, 1, 1, 11, 59))
    make_photo(tmp_path / "m" / "two" / "x.jpg", datetime(2023, 1, 1), color=(1, 1, 1))
    import_chat(conn, [tmp_path / "c"])
    import_media(conn, [tmp_path / "m"], paths)
    associate(conn)
    linked = conn.execute("SELECT rel_path, association_confidence FROM media WHERE message_id IS NOT NULL").fetchall()
    assert len(linked) == 1 and linked[0]["association_confidence"] == "high"
    assert linked[0]["rel_path"].startswith("one")


def test_media_without_trusted_time_adopts_chat_time(conn, paths, tmp_path):
    import os

    write_json(tmp_path / "c" / "c.json", [{"id": 1, "time": "2024-01-01 12:00:00", "sender": "A", "media": "abc.jpg"}])
    p = make_photo(tmp_path / "m" / "abc.jpg", None)
    os.utime(p, (datetime(2025, 5, 5).timestamp(),) * 2)
    import_chat(conn, [tmp_path / "c"])
    import_media(conn, [tmp_path / "m"], paths)
    associate(conn)
    r = media_row(conn, "abc.jpg")
    assert (r["ts"], r["ts_source"]) == ("2024-01-01T12:00:00", "chat")
    associate(conn)  # idempotent
    assert media_row(conn, "abc.jpg")["ts_source"] == "chat"


def test_manual_decisions_survive_reassociation(conn, imported):
    auto = media_row(conn, "IMG_20240302_205950.jpg")
    link_manually(conn, auto["id"], None)
    unlinked = media_row(conn, "IMG_20240304_100000.jpg")
    target = conn.execute("SELECT id FROM messages WHERE source_message_id = '6'").fetchone()[0]
    link_manually(conn, unlinked["id"], target)
    associate(conn)
    assert media_row(conn, "IMG_20240302_205950.jpg")["message_id"] is None
    r = media_row(conn, "IMG_20240304_100000.jpg")
    assert (r["message_id"], r["association_method"]) == (target, "manual")
    reset_manual(conn, auto["id"])
    associate(conn)
    assert media_row(conn, "IMG_20240302_205950.jpg")["association_confidence"] == "high"
