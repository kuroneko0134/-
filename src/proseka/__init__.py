"""Project SEKAI (プロジェクトセカイ) master-data integration.

Reads the publicly published master database for every server region and
exposes it as typed Python objects and a command line tool. Unofficial: it is
not affiliated with SEGA, Colorful Palette or Crypton Future Media.
"""

from __future__ import annotations

from .client import CORE_TABLES, DEFAULT_TTL, ProsekaClient
from .collection import ChartProgress, Collection, EventPace, LevelSummary, MarkResult
from .errors import OfflineError, ProsekaError, TableNotFound, TransportError
from .models import Card, Character, Event, Music, MusicDifficulty, Unit
from .play import ClearType, OwnedCard, PlayerProfile, PlayRecord, parse_difficulty
from .regions import DEFAULT_REGION, REGIONS, Region, get_region
from .store import PlayerStore, default_data_dir
from .transport import Response, Transport, UrllibTransport

__version__ = "0.1.0"

__all__ = [
    "ProsekaClient",
    "CORE_TABLES",
    "DEFAULT_TTL",
    "Card",
    "Character",
    "Event",
    "Music",
    "MusicDifficulty",
    "Unit",
    "Collection",
    "ChartProgress",
    "LevelSummary",
    "MarkResult",
    "EventPace",
    "PlayerStore",
    "PlayerProfile",
    "PlayRecord",
    "OwnedCard",
    "ClearType",
    "parse_difficulty",
    "default_data_dir",
    "Region",
    "REGIONS",
    "DEFAULT_REGION",
    "get_region",
    "Response",
    "Transport",
    "UrllibTransport",
    "ProsekaError",
    "TransportError",
    "TableNotFound",
    "OfflineError",
    "__version__",
]
