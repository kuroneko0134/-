"""On-disk cache for downloaded master tables."""

from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

__all__ = ["CacheEntry", "TableCache", "default_cache_dir"]


def default_cache_dir() -> Path:
    """Return the cache root, honouring ``PROSEKA_CACHE_DIR`` and ``XDG_CACHE_HOME``."""
    override = os.environ.get("PROSEKA_CACHE_DIR")
    if override:
        return Path(override).expanduser()
    xdg = os.environ.get("XDG_CACHE_HOME")
    root = Path(xdg).expanduser() if xdg else Path.home() / ".cache"
    return root / "proseka"


@dataclass(frozen=True)
class CacheEntry:
    """A cached table together with the metadata used to revalidate it."""

    payload: Any
    etag: Optional[str]
    fetched_at: float

    def age(self, now: Optional[float] = None) -> float:
        return max(0.0, (time.time() if now is None else now) - self.fetched_at)

    def is_fresh(self, ttl: float, now: Optional[float] = None) -> bool:
        return self.age(now) < ttl


class TableCache:
    """Stores one JSON file plus one metadata file per table, per region."""

    def __init__(self, root: Path, region: str) -> None:
        self.dir = Path(root) / region

    def _data_path(self, table: str) -> Path:
        return self.dir / f"{table}.json"

    def _meta_path(self, table: str) -> Path:
        return self.dir / f"{table}.meta.json"

    def read(self, table: str) -> Optional[CacheEntry]:
        data_path = self._data_path(table)
        if not data_path.is_file():
            return None
        try:
            payload = json.loads(data_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        etag = None
        fetched_at = data_path.stat().st_mtime
        meta_path = self._meta_path(table)
        if meta_path.is_file():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                etag = meta.get("etag")
                fetched_at = float(meta.get("fetched_at", fetched_at))
            except (OSError, ValueError, TypeError):
                pass
        return CacheEntry(payload=payload, etag=etag, fetched_at=fetched_at)

    def write(self, table: str, payload: Any, etag: Optional[str] = None) -> CacheEntry:
        self.dir.mkdir(parents=True, exist_ok=True)
        fetched_at = time.time()
        _atomic_write(self._data_path(table), json.dumps(payload, ensure_ascii=False))
        _atomic_write(
            self._meta_path(table),
            json.dumps({"etag": etag, "fetched_at": fetched_at}, ensure_ascii=False),
        )
        return CacheEntry(payload=payload, etag=etag, fetched_at=fetched_at)

    def touch(self, table: str, entry: CacheEntry) -> CacheEntry:
        """Record that a cached table was revalidated without being re-downloaded."""
        return self.write(table, entry.payload, entry.etag)

    def clear(self) -> int:
        """Delete every cached table for this region and return the file count."""
        if not self.dir.is_dir():
            return 0
        removed = 0
        for path in sorted(self.dir.glob("*.json")):
            path.unlink()
            removed += 1
        return removed


def _atomic_write(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
