from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COPY_FILE = REPO_ROOT / "config" / "copy.json"
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"
DEMO_DATA_DIR = REPO_ROOT / "demo-data"

DATA_DIR_ENV = "MEMORY_MUSEUM_DATA"


@dataclass(frozen=True)
class Paths:
    """Every file the app writes lives under one local data directory."""

    root: Path

    @property
    def db(self) -> Path:
        return self.root / "museum.db"

    @property
    def staging_db(self) -> Path:
        return self.root / "museum.staging.db"

    @property
    def cache(self) -> Path:
        return self.root / "cache"

    @property
    def thumbs(self) -> Path:
        return self.cache / "thumbs"

    @property
    def playable(self) -> Path:
        return self.cache / "playable"

    @property
    def avatars(self) -> Path:
        return self.root / "avatars"

    def ensure(self) -> "Paths":
        for p in (self.root, self.cache, self.thumbs, self.playable, self.avatars):
            p.mkdir(parents=True, exist_ok=True)
        return self


def resolve_paths(data_dir: str | os.PathLike | None = None) -> Paths:
    raw = data_dir or os.environ.get(DATA_DIR_ENV) or "data"
    return Paths(Path(raw).expanduser().resolve())
