"""Shared test helpers: fixture loading and an offline transport double."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional

from proseka.errors import TableNotFound, TransportError
from proseka.transport import Response

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_bytes(table: str) -> bytes:
    path = FIXTURES / f"{table}.json"
    if not path.is_file():
        raise TableNotFound(f"no fixture for {table}")
    return path.read_bytes()


def seed_cache(cache_root: Path, region: str = "jp") -> Path:
    """Copy every fixture into a cache directory so a client can read it offline."""
    target = Path(cache_root) / region
    target.mkdir(parents=True, exist_ok=True)
    for path in FIXTURES.glob("*.json"):
        shutil.copy(path, target / path.name)
    return target


class FakeTransport:
    """Serves fixtures, records every request and can be told to fail."""

    def __init__(self, etag: Optional[str] = '"v1"', fail: bool = False) -> None:
        self.requests: List[str] = []
        self.conditional: List[Optional[str]] = []
        self.etag = etag
        self.fail = fail
        self.payloads: Dict[str, bytes] = {}

    def set_payload(self, table: str, records) -> None:
        self.payloads[table] = json.dumps(records, ensure_ascii=False).encode("utf-8")

    def get(self, url: str, etag: Optional[str] = None) -> Response:
        self.requests.append(url)
        self.conditional.append(etag)
        if self.fail:
            raise TransportError(f"simulated network failure for {url}")
        table = url.rsplit("/", 1)[-1].removesuffix(".json")
        if etag and etag == self.etag:
            return Response(body=None, etag=etag, not_modified=True)
        body = self.payloads.get(table) or fixture_bytes(table)
        return Response(body=body, etag=self.etag)

    @property
    def call_count(self) -> int:
        return len(self.requests)
