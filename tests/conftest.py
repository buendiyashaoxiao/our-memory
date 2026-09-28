from __future__ import annotations

import json
import math
import shutil
import struct
import wave
from datetime import datetime
from pathlib import Path

import pytest
from PIL import Image

from memory_museum.config import DEMO_DATA_DIR, Paths
from memory_museum.db import open_db
from memory_museum.demo_gen import _exif_bytes

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def paths(tmp_path: Path) -> Paths:
    return Paths(tmp_path / "data").ensure()


@pytest.fixture
def conn(paths: Paths):
    c = open_db(paths.db)
    yield c
    c.close()


def make_photo(path: Path, taken: datetime | None, size=(64, 48), color=(120, 90, 60), orientation: int = 1) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path, "JPEG", exif=_exif_bytes(taken, orientation))
    return path


def make_wav(path: Path, seconds: float = 1.0, rate: int = 8000) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(i / 5) * (i / (rate * seconds))))
                               for i in range(int(rate * seconds))))
    return path


def write_json(path: Path, messages: list, **extra) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"messages": messages, **extra}, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture
def small_archive(tmp_path: Path) -> dict[str, Path]:
    """A tiny hand-made archive with known answers."""
    chat = tmp_path / "src" / "chat"
    media = tmp_path / "src" / "media"
    msgs = [
        {"id": "1", "time": "2024-03-01 09:00:00", "sender_id": "a", "sender_name": "阿林", "text": "早安"},
        {"id": "2", "time": "2024-03-01 09:01:00", "sender_id": "b", "sender_name": "小周", "text": "早呀，今天下雨了"},
        {"id": "3", "time": "2024-03-01 20:00:00", "sender_id": "a", "type": "image", "media": "IMG_20240301_195930.jpg"},
        {"id": "4", "time": "2024-03-01 20:05:00", "sender_id": "b", "type": "voice", "media": "voice_1.wav", "duration": 1},
        {"id": "5", "time": "2024-03-02 21:00:00", "sender_id": "a", "type": "image"},  # fuzzy target
        {"id": "6", "time": "2024-03-02 21:02:00", "sender_id": "b", "text": "好看！"},
        {"id": "7", "time": "2024-03-05 12:00:00", "sender_id": "a", "type": "image", "media": "missing.jpg"},
    ]
    for i in range(8):
        msgs.append({"id": f"q{i}", "time": f"2024-03-03 22:{10 + i}:00", "sender_id": "ab"[i % 2], "text": f"聊天{i} 哈哈哈"})
    write_json(chat / "chat.json", msgs, participants=[{"id": "a", "name": "阿林"}, {"id": "b", "name": "小周"}])
    make_photo(media / "IMG_20240301_195930.jpg", datetime(2024, 3, 1, 19, 59, 30))
    make_photo(media / "IMG_20240302_205950.jpg", datetime(2024, 3, 2, 20, 59, 50), color=(20, 40, 90))
    make_photo(media / "IMG_20240304_100000.jpg", datetime(2024, 3, 4, 10, 0, 0), color=(200, 40, 90))  # unlinked
    make_wav(media / "voice" / "voice_1.wav")
    return {"chat": chat, "media": media}


@pytest.fixture(scope="session")
def demo_db(tmp_path_factory) -> Paths:
    """The committed demo dataset imported once for integration tests."""
    from memory_museum.pipeline import commit_staging, open_staging, run_import

    root = tmp_path_factory.mktemp("demo")
    src = root / "demo-data"
    shutil.copytree(DEMO_DATA_DIR, src)
    p = Paths(root / "data").ensure()
    staging = open_staging(p)
    try:
        run_import(staging, p, chat_inputs=[src / "chat"], media_inputs=[src / "media"])
    finally:
        staging.close()
    commit_staging(p)
    return p
