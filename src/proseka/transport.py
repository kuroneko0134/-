"""HTTP access to the master-data mirrors, kept separate so tests can replace it."""

from __future__ import annotations

import gzip
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional, Protocol

from .errors import TableNotFound, TransportError

__all__ = ["Response", "Transport", "UrllibTransport", "USER_AGENT"]

USER_AGENT = "proseka/0.1 (+https://github.com/Sekai-World/sekai-master-db-diff)"


@dataclass(frozen=True)
class Response:
    """Either a body, or ``not_modified`` when the cached copy is still current."""

    body: Optional[bytes]
    etag: Optional[str] = None
    not_modified: bool = False


class Transport(Protocol):
    """Fetches one URL, optionally revalidating a cached ETag."""

    def get(self, url: str, etag: Optional[str] = None) -> Response:  # pragma: no cover
        ...


class UrllibTransport:
    """Standard-library HTTP client. Honours ``HTTPS_PROXY`` like any urllib call."""

    def __init__(self, timeout: float = 30.0, user_agent: str = USER_AGENT) -> None:
        self.timeout = timeout
        self.user_agent = user_agent

    def get(self, url: str, etag: Optional[str] = None) -> Response:
        request = urllib.request.Request(url, method="GET")
        request.add_header("User-Agent", self.user_agent)
        request.add_header("Accept", "application/json")
        request.add_header("Accept-Encoding", "gzip")
        if etag:
            request.add_header("If-None-Match", etag)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read()
                if response.headers.get("Content-Encoding", "").lower() == "gzip":
                    body = gzip.decompress(body)
                return Response(body=body, etag=response.headers.get("ETag"))
        except urllib.error.HTTPError as exc:
            if exc.code == 304:
                return Response(body=None, etag=etag, not_modified=True)
            if exc.code == 404:
                raise TableNotFound(f"no such master table: {url}") from exc
            raise TransportError(f"HTTP {exc.code} while fetching {url}") from exc
        except urllib.error.URLError as exc:
            raise TransportError(f"could not reach {url}: {exc.reason}") from exc
        except OSError as exc:
            raise TransportError(f"could not reach {url}: {exc}") from exc
