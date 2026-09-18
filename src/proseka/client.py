"""The client that ties regions, transport, cache and models together."""

from __future__ import annotations

import json
import logging
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from .cache import TableCache, default_cache_dir
from .errors import OfflineError, ProsekaError, TransportError
from .models import Card, Character, Event, Music, MusicDifficulty, Unit
from .regions import DEFAULT_REGION, Region, get_region
from .transport import Transport, UrllibTransport

__all__ = ["ProsekaClient", "CORE_TABLES", "DEFAULT_TTL"]

logger = logging.getLogger("proseka")

#: Tables the typed accessors rely on; ``sync`` downloads these by default.
CORE_TABLES: Tuple[str, ...] = (
    "gameCharacters",
    "unitProfiles",
    "musics",
    "musicDifficulties",
    "cards",
    "events",
)

#: How long a cached table is trusted without revalidating it (6 hours).
DEFAULT_TTL = 6 * 60 * 60


def _normalize(text: Any) -> str:
    """Fold width, case and spacing so 'ミク' matches 'ﾐｸ' and 'Miku' matches 'MIKU'."""
    if text is None:
        return ""
    folded = unicodedata.normalize("NFKC", str(text)).casefold()
    return "".join(folded.split())


class ProsekaClient:
    """Reads Project SEKAI master data, caching it on disk between runs.

    The data comes from the community-maintained Sekai-World mirrors, not from
    the game servers, so no account or credential is involved.
    """

    def __init__(
        self,
        region: str = DEFAULT_REGION,
        *,
        cache_dir: Optional[Path] = None,
        ttl: float = DEFAULT_TTL,
        offline: bool = False,
        transport: Optional[Transport] = None,
    ) -> None:
        self.region: Region = get_region(region)
        self.ttl = float(ttl)
        self.offline = offline
        self.cache_root = Path(cache_dir) if cache_dir else default_cache_dir()
        self.cache = TableCache(self.cache_root, self.region.code)
        self.transport: Transport = transport or UrllibTransport()
        self._parsed: Dict[str, Any] = {}

    # ------------------------------------------------------------------ raw

    def table(self, name: str, *, refresh: bool = False) -> List[Dict[str, Any]]:
        """Return one master table as a list of raw records."""
        entry = self.cache.read(name)
        if entry is not None and not refresh and entry.is_fresh(self.ttl):
            return entry.payload

        if self.offline:
            if entry is not None:
                return entry.payload
            raise OfflineError(
                f"table {name!r} is not cached for region {self.region.code!r}; "
                "run a sync with offline mode turned off first"
            )

        url = self.region.table_url(name)
        try:
            response = self.transport.get(url, etag=entry.etag if entry else None)
        except TransportError:
            if entry is not None:
                logger.warning("using stale cache for %s: download failed", name)
                return entry.payload
            raise

        if response.not_modified and entry is not None:
            self.cache.touch(name, entry)
            return entry.payload
        if response.body is None:
            if entry is not None:
                return entry.payload
            raise TransportError(f"empty response for {url}")

        try:
            payload = json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise ProsekaError(f"{url} did not contain valid JSON: {exc}") from exc
        self.cache.write(name, payload, response.etag)
        self._parsed.pop(name, None)
        return payload

    def sync(self, tables: Optional[Sequence[str]] = None) -> Dict[str, int]:
        """Download the given tables (the core set by default); returns record counts."""
        counts: Dict[str, int] = {}
        for name in tables or CORE_TABLES:
            counts[name] = len(self.table(name, refresh=True))
        return counts

    def clear_cache(self) -> int:
        """Delete this region's cached tables and return how many files were removed."""
        self._parsed.clear()
        return self.cache.clear()

    def _typed(self, name: str, parser, refresh: bool = False) -> List[Any]:
        if refresh or name not in self._parsed:
            self._parsed[name] = [parser(row) for row in self.table(name, refresh=refresh)]
        return self._parsed[name]

    # ----------------------------------------------------------- collections

    def units(self, *, refresh: bool = False) -> List[Unit]:
        return self._typed("unitProfiles", Unit.parse, refresh)

    def characters(self, *, refresh: bool = False) -> List[Character]:
        return self._typed("gameCharacters", Character.parse, refresh)

    def musics(self, *, refresh: bool = False) -> List[Music]:
        return self._typed("musics", Music.parse, refresh)

    def music_difficulties(self, *, refresh: bool = False) -> List[MusicDifficulty]:
        return self._typed("musicDifficulties", MusicDifficulty.parse, refresh)

    def cards(self, *, refresh: bool = False) -> List[Card]:
        return self._typed("cards", Card.parse, refresh)

    def events(self, *, refresh: bool = False) -> List[Event]:
        return self._typed("events", Event.parse, refresh)

    # --------------------------------------------------------------- lookups

    def unit(self, code: str) -> Optional[Unit]:
        """Find a band by its internal code or by its display name."""
        wanted = _normalize(code)
        for unit in self.units():
            if wanted in {_normalize(unit.unit), _normalize(unit.name), _normalize(unit.profile_name)}:
                return unit
        return None

    def character(self, character_id: int) -> Optional[Character]:
        for character in self.characters():
            if character.id == int(character_id):
                return character
        return None

    def find_characters(self, query: str) -> List[Character]:
        """Search characters by any part of their Japanese, kana or English name."""
        wanted = _normalize(query)
        if not wanted:
            return []
        found: List[Character] = []
        for character in self.characters():
            haystack = (
                character.full_name,
                character.full_name_ruby,
                character.full_name_english,
                character.first_name,
                character.given_name,
                character.first_name_ruby,
                character.given_name_ruby,
                character.first_name_english,
                character.given_name_english,
            )
            if any(wanted in _normalize(part) for part in haystack if part):
                found.append(character)
        return found

    def characters_in_unit(self, code: str) -> List[Character]:
        """Every character belonging to a band, in game order."""
        unit = self.unit(code)
        key = unit.unit if unit else _normalize(code)
        return [c for c in self.characters() if c.unit == key]

    def music(self, music_id: int) -> Optional[Music]:
        for music in self.musics():
            if music.id == int(music_id):
                return music
        return None

    def find_musics(self, query: str) -> List[Music]:
        """Search songs by title, reading, lyricist, composer or arranger."""
        wanted = _normalize(query)
        if not wanted:
            return []
        return [
            music
            for music in self.musics()
            if any(
                wanted in _normalize(part)
                for part in (music.title, music.pronunciation, music.lyricist, music.composer, music.arranger)
                if part
            )
        ]

    def difficulties_for(self, music_id: int) -> List[MusicDifficulty]:
        """Every chart of one song, easiest first."""
        order = {"easy": 0, "normal": 1, "hard": 2, "expert": 3, "master": 4, "append": 5}
        charts = [d for d in self.music_difficulties() if d.music_id == int(music_id)]
        return sorted(charts, key=lambda d: (order.get(d.difficulty, 99), d.play_level))

    def charts_at_level(
        self, play_level: int, difficulty: Optional[str] = None
    ) -> List[Tuple[Music, MusicDifficulty]]:
        """All charts of a given level, newest song last, paired with their song."""
        by_id = {music.id: music for music in self.musics()}
        wanted = difficulty.lower() if difficulty else None
        pairs = [
            (by_id[chart.music_id], chart)
            for chart in self.music_difficulties()
            if chart.play_level == int(play_level)
            and (wanted is None or chart.difficulty == wanted)
            and chart.music_id in by_id
        ]
        return sorted(pairs, key=lambda pair: pair[0].id)

    def card(self, card_id: int) -> Optional[Card]:
        for card in self.cards():
            if card.id == int(card_id):
                return card
        return None

    def cards_for_character(
        self,
        character: Union[int, Character],
        *,
        rarity: Optional[str] = None,
        attr: Optional[str] = None,
    ) -> List[Card]:
        """Cards of one character, optionally narrowed by rarity or attribute."""
        character_id = character.id if isinstance(character, Character) else int(character)
        wanted_rarity = _canonical_rarity(rarity) if rarity else None
        wanted_attr = attr.lower() if attr else None
        return [
            card
            for card in self.cards()
            if card.character_id == character_id
            and (wanted_rarity is None or card.rarity == wanted_rarity)
            and (wanted_attr is None or card.attr == wanted_attr)
        ]

    def event(self, event_id: int) -> Optional[Event]:
        for event in self.events():
            if event.id == int(event_id):
                return event
        return None

    def current_event(self, now: Optional[datetime] = None) -> Optional[Event]:
        """The event being played right now, if any."""
        moment = _aware(now)
        for event in self.events():
            if event.is_running(moment):
                return event
        return None

    def next_event(self, now: Optional[datetime] = None) -> Optional[Event]:
        """The next event that has not started yet."""
        moment = _aware(now)
        upcoming = [e for e in self.events() if e.start_at and e.start_at > moment]
        return min(upcoming, key=lambda e: e.start_at) if upcoming else None

    def recent_events(self, limit: int = 5, now: Optional[datetime] = None) -> List[Event]:
        """The most recently started events, newest first."""
        moment = _aware(now)
        started = [e for e in self.events() if e.start_at and e.start_at <= moment]
        started.sort(key=lambda e: e.start_at, reverse=True)
        return started[: max(0, int(limit))]


def _aware(moment: Optional[datetime]) -> datetime:
    if moment is None:
        return datetime.now(timezone.utc)
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _canonical_rarity(value: str) -> str:
    """Accept ``4``, ``4*``, ``★4``, ``rarity_4`` or ``birthday`` for the same rarity."""
    text = str(value).strip().lower().strip("*★☆ ")
    if text.startswith("rarity_"):
        return text
    if text in {"birthday", "bd"}:
        return "rarity_birthday"
    return f"rarity_{text}"
