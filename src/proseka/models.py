"""Typed views over the raw master-data records."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

__all__ = [
    "Unit",
    "Character",
    "Music",
    "MusicDifficulty",
    "Card",
    "Event",
    "from_epoch_ms",
    "to_epoch_ms",
]


def from_epoch_ms(value: Any) -> Optional[datetime]:
    """Convert a millisecond timestamp to an aware UTC datetime."""
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(float(value) / 1000.0, tz=timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def to_epoch_ms(moment: datetime) -> int:
    """Convert a datetime to a millisecond timestamp, assuming UTC when naive."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return int(moment.timestamp() * 1000)


@dataclass(frozen=True)
class _Record:
    """Common base: every model keeps the untouched source record in ``raw``."""

    raw: Mapping[str, Any] = field(repr=False)

    def get(self, key: str, default: Any = None) -> Any:
        """Read a field straight from the source record, including ones not modelled."""
        return self.raw.get(key, default)


@dataclass(frozen=True)
class Unit(_Record):
    """A band, such as Leo/need or Vivid BAD SQUAD."""

    unit: str = ""
    name: str = ""
    profile_name: str = ""
    color_code: str = ""
    profile_sentence: str = ""
    seq: int = 0

    @classmethod
    def parse(cls, raw: Mapping[str, Any]) -> "Unit":
        return cls(
            raw=raw,
            unit=raw.get("unit", ""),
            name=raw.get("unitName", ""),
            profile_name=raw.get("unitProfileName", raw.get("unitName", "")),
            color_code=raw.get("colorCode", ""),
            profile_sentence=raw.get("profileSentence", ""),
            seq=int(raw.get("seq", 0) or 0),
        )


@dataclass(frozen=True)
class Character(_Record):
    """A playable character."""

    id: int = 0
    first_name: str = ""
    given_name: str = ""
    first_name_ruby: str = ""
    given_name_ruby: str = ""
    first_name_english: str = ""
    given_name_english: str = ""
    unit: str = ""
    gender: str = ""
    height: Optional[float] = None
    support_unit_type: str = ""

    @classmethod
    def parse(cls, raw: Mapping[str, Any]) -> "Character":
        height = raw.get("height")
        return cls(
            raw=raw,
            id=int(raw.get("id", 0) or 0),
            first_name=raw.get("firstName", ""),
            given_name=raw.get("givenName", ""),
            first_name_ruby=raw.get("firstNameRuby", ""),
            given_name_ruby=raw.get("givenNameRuby", ""),
            first_name_english=raw.get("firstNameEnglish", ""),
            given_name_english=raw.get("givenNameEnglish", ""),
            unit=raw.get("unit", ""),
            gender=raw.get("gender", ""),
            height=float(height) if height is not None else None,
            support_unit_type=raw.get("supportUnitType", ""),
        )

    @property
    def full_name(self) -> str:
        """Family name then given name, as the game prints it."""
        return " ".join(part for part in (self.first_name, self.given_name) if part)

    @property
    def full_name_ruby(self) -> str:
        return " ".join(p for p in (self.first_name_ruby, self.given_name_ruby) if p)

    @property
    def full_name_english(self) -> str:
        """Given name then family name, title-cased from the upper-case source."""
        parts = [p.title() for p in (self.given_name_english, self.first_name_english) if p]
        return " ".join(parts)

    @property
    def is_virtual_singer(self) -> bool:
        return self.unit == "piapro"


@dataclass(frozen=True)
class Music(_Record):
    """A song."""

    id: int = 0
    title: str = ""
    pronunciation: str = ""
    lyricist: str = ""
    composer: str = ""
    arranger: str = ""
    published_at: Optional[datetime] = None
    released_at: Optional[datetime] = None
    is_full_length: bool = False
    is_newly_written: bool = False
    assetbundle_name: str = ""

    @classmethod
    def parse(cls, raw: Mapping[str, Any]) -> "Music":
        return cls(
            raw=raw,
            id=int(raw.get("id", 0) or 0),
            title=raw.get("title", ""),
            pronunciation=raw.get("pronunciation", ""),
            lyricist=raw.get("lyricist", ""),
            composer=raw.get("composer", ""),
            arranger=raw.get("arranger", ""),
            published_at=from_epoch_ms(raw.get("publishedAt")),
            released_at=from_epoch_ms(raw.get("releasedAt")),
            is_full_length=bool(raw.get("isFullLength", False)),
            is_newly_written=bool(raw.get("isNewlyWrittenMusic", False)),
            assetbundle_name=raw.get("assetbundleName", ""),
        )

    @property
    def credit(self) -> str:
        """The distinct names behind the song, in lyricist/composer/arranger order."""
        names: list[str] = []
        for name in (self.lyricist, self.composer, self.arranger):
            if name and name not in names:
                names.append(name)
        return " / ".join(names)


@dataclass(frozen=True)
class MusicDifficulty(_Record):
    """One chart of one song, such as MASTER 32."""

    id: int = 0
    music_id: int = 0
    difficulty: str = ""
    play_level: int = 0
    total_note_count: int = 0

    @classmethod
    def parse(cls, raw: Mapping[str, Any]) -> "MusicDifficulty":
        return cls(
            raw=raw,
            id=int(raw.get("id", 0) or 0),
            music_id=int(raw.get("musicId", 0) or 0),
            difficulty=raw.get("musicDifficulty", ""),
            play_level=int(raw.get("playLevel", 0) or 0),
            total_note_count=int(raw.get("totalNoteCount", 0) or 0),
        )

    @property
    def label(self) -> str:
        return f"{self.difficulty.upper()} {self.play_level}"


@dataclass(frozen=True)
class Card(_Record):
    """A character card."""

    id: int = 0
    character_id: int = 0
    rarity: str = ""
    attr: str = ""
    prefix: str = ""
    skill_name: str = ""
    support_unit: str = ""
    assetbundle_name: str = ""
    release_at: Optional[datetime] = None

    @classmethod
    def parse(cls, raw: Mapping[str, Any]) -> "Card":
        return cls(
            raw=raw,
            id=int(raw.get("id", 0) or 0),
            character_id=int(raw.get("characterId", 0) or 0),
            rarity=raw.get("cardRarityType", ""),
            attr=raw.get("attr", ""),
            prefix=raw.get("prefix", ""),
            skill_name=raw.get("cardSkillName", ""),
            support_unit=raw.get("supportUnit", ""),
            assetbundle_name=raw.get("assetbundleName", ""),
            release_at=from_epoch_ms(raw.get("releaseAt")),
        )

    @property
    def rarity_stars(self) -> str:
        """``rarity_4`` becomes ``★★★★``; birthday cards become a single bloom."""
        if self.rarity == "rarity_birthday":
            return "🎂"
        _, _, digits = self.rarity.partition("rarity_")
        return "★" * int(digits) if digits.isdigit() else self.rarity


@dataclass(frozen=True)
class Event(_Record):
    """An in-game event."""

    id: int = 0
    name: str = ""
    event_type: str = ""
    unit: str = ""
    start_at: Optional[datetime] = None
    aggregate_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    assetbundle_name: str = ""

    @classmethod
    def parse(cls, raw: Mapping[str, Any]) -> "Event":
        return cls(
            raw=raw,
            id=int(raw.get("id", 0) or 0),
            name=raw.get("name", ""),
            event_type=raw.get("eventType", ""),
            unit=raw.get("unit", ""),
            start_at=from_epoch_ms(raw.get("startAt")),
            aggregate_at=from_epoch_ms(raw.get("aggregateAt")),
            closed_at=from_epoch_ms(raw.get("closedAt")),
            assetbundle_name=raw.get("assetbundleName", ""),
        )

    def is_running(self, now: Optional[datetime] = None) -> bool:
        """True while the event accepts play, i.e. between start and ranking cut-off."""
        moment = now or datetime.now(timezone.utc)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        end = self.aggregate_at or self.closed_at
        if self.start_at is None or end is None:
            return False
        return self.start_at <= moment <= end
