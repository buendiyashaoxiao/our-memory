import os
import shutil
from datetime import datetime
from pathlib import Path

import pytest

from memory_museum.media import ffmpeg
from memory_museum.media.metadata import classify, extract, quick_hash
from memory_museum.media.scanner import import_media

from .conftest import FIXTURES, make_photo, make_wav

CORRUPT = FIXTURES / "corrupted"


def test_classify():
    assert classify(Path("a.JPG")) == "image"
    assert classify(Path("a.mov")) == "video"
    assert classify(Path("song.mp3")) == "audio"
    assert classify(Path("chat/voice/abc.m4a")) == "voice"
    assert classify(Path("x.amr")) == "voice"
    assert classify(Path("PTT-20240101-WA0001.opus")) == "voice"
    assert classify(Path("notes.pdf")) is None


def test_image_exif_timestamp_dimensions_and_thumbnail(paths, tmp_path):
    p = make_photo(tmp_path / "a.jpg", datetime(2024, 5, 1, 8, 30, 0), size=(80, 40))
    info = extract(p, tmp_path, paths.thumbs, paths.playable)
    assert info["status"] == "ok"
    assert info["ts"] == "2024-05-01T08:30:00" and info["ts_source"] == "exif"
    assert (info["width"], info["height"]) == (80, 40)
    assert Path(info["thumb_path"]).exists()


def test_exif_orientation_swaps_dimensions(paths, tmp_path):
    p = make_photo(tmp_path / "r.jpg", datetime(2024, 5, 1), size=(80, 40), orientation=6)
    info = extract(p, tmp_path, paths.thumbs, paths.playable)
    assert info["orientation"] == 6
    assert (info["width"], info["height"]) == (40, 80)


def test_timestamp_fallbacks_filename_then_mtime(paths, tmp_path):
    named = make_photo(tmp_path / "IMG_20240102_030405.jpg", None)
    info = extract(named, tmp_path, paths.thumbs, paths.playable)
    assert (info["ts"], info["ts_source"]) == ("2024-01-02T03:04:05", "filename")
    plain = make_photo(tmp_path / "plain.jpg", None)
    os.utime(plain, (datetime(2023, 6, 7, 8, 9, 10).timestamp(),) * 2)
    info = extract(plain, tmp_path, paths.thumbs, paths.playable)
    assert (info["ts"], info["ts_source"]) == ("2023-06-07T08:09:10", "mtime")


@pytest.mark.parametrize("name", ["broken.jpg", "broken.wav", "empty.mp4"])
def test_corrupt_files_fail_gracefully(paths, name):
    info = extract(CORRUPT / name, CORRUPT, paths.thumbs, paths.playable)
    assert info["status"] == "corrupt"
    assert info["error"]


def test_wav_duration_and_real_waveform(paths, tmp_path):
    p = make_wav(tmp_path / "voice" / "v.wav", seconds=2.0)
    info = extract(p, tmp_path, paths.thumbs, paths.playable)
    assert info["media_type"] == "voice"
    assert info["duration"] == pytest.approx(2.0, abs=0.05)
    peaks = info["waveform"]
    assert peaks and max(peaks) == 1.0 and peaks[0] < peaks[-1]  # the test tone fades in


@pytest.mark.skipif(not ffmpeg.find_ffmpeg(), reason="ffmpeg not available")
def test_video_metadata_and_thumbnail(paths, tmp_path):
    from memory_museum.demo_gen import save_video
    import random

    p = tmp_path / "VID_20240101_101010.mp4"
    assert save_video(p, "sea", 1.0, random.Random(1))
    info = extract(p, tmp_path, paths.thumbs, paths.playable)
    assert info["status"] == "ok"
    assert info["duration"] == pytest.approx(1.0, abs=0.2)
    assert (info["width"], info["height"]) == (360, 640)
    assert Path(info["thumb_path"]).exists()


def test_quick_hash_detects_identical_content(tmp_path):
    a = make_photo(tmp_path / "a.jpg", None)
    b = tmp_path / "b.jpg"
    shutil.copy(a, b)
    c = make_photo(tmp_path / "c.jpg", None, color=(1, 2, 3))
    assert quick_hash(a) == quick_hash(b) != quick_hash(c)


def test_scan_is_incremental_and_marks_duplicates_and_missing(conn, paths, tmp_path):
    src = tmp_path / "media"
    a = make_photo(src / "a.jpg", datetime(2024, 1, 1))
    shutil.copy(a, src / "copy_of_a.jpg")
    make_photo(src / "b.jpg", datetime(2024, 1, 2), color=(9, 9, 9))
    (src / "notes.txt").write_text("x")
    rep = import_media(conn, [src], paths)
    assert (rep.new, rep.unsupported_files, rep.duplicates) == (3, 1, 1)

    rep2 = import_media(conn, [src], paths)
    assert rep2.unchanged == 3 and rep2.new == 0

    (src / "b.jpg").unlink()
    rep3 = import_media(conn, [src], paths)
    assert rep3.missing_marked == 1
    assert conn.execute("SELECT status FROM media WHERE original_filename = 'b.jpg'").fetchone()[0] == "missing"


def test_one_broken_file_does_not_stop_the_scan(conn, paths, tmp_path):
    src = tmp_path / "media"
    shutil.copytree(CORRUPT, src)
    make_photo(src / "good.jpg", datetime(2024, 1, 1))
    rep = import_media(conn, [src], paths)
    assert rep.by_status["ok"] == 1
    assert rep.by_status["corrupt"] == 3


def test_manual_date_survives_rescan(conn, paths, tmp_path):
    from memory_museum.curation import update_media

    src = tmp_path / "media"
    make_photo(src / "a.jpg", datetime(2024, 1, 1))
    import_media(conn, [src], paths)
    mid = conn.execute("SELECT id FROM media").fetchone()[0]
    update_media(conn, mid, {"ts": "2020-02-02 02:02"})
    os.utime(src / "a.jpg")  # force re-extraction
    import_media(conn, [src], paths)
    assert conn.execute("SELECT ts, ts_source FROM media").fetchone()[:] == ("2020-02-02T02:02:00", "manual")
