"""Exceptions raised by the proseka package."""

from __future__ import annotations

__all__ = ["ProsekaError", "TransportError", "TableNotFound", "OfflineError"]


class ProsekaError(Exception):
    """Base class for every error raised by this package."""


class TransportError(ProsekaError):
    """The master data could not be downloaded."""


class TableNotFound(ProsekaError):
    """The requested master table does not exist for this region."""


class OfflineError(ProsekaError):
    """Offline mode was requested but the table is not cached yet."""
