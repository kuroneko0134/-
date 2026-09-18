"""Your own play data: what the app shows on your phone, kept on your machine.

The game has no public API and its save data stays inside the app sandbox, so
these records are the ones you enter or import yourself. They are joined
against the master data to answer questions the app does not answer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from typing import Any, Dict, Mapping, Optional

__all__ = ["ClearType", "PlayRecord", "OwnedCard", "PlayerProfile", "DIFFICULTIES", "parse_difficulty"]

#: Chart difficulties, easiest first.
DIFFICULTIES = ("easy", "normal", "hard", "expert", "master", "append")

_DIFFICULTY_ALIASES = {
    "ez": "easy",
    "nm": "normal",
    "hd": "hard",
    "ex": "expert",
    "ma": "master",
    "mas": "master",
    "ap_diff": "append",
    "apd": "append",
    "イージー": "easy",
    "ノーマル": "normal",
    "ハード": "hard",
    "エキスパート": "expert",
    "マスター": "master",
    "アペンド": "append",
}


def parse_difficulty(value: str) -> str:
    """Accept ``master``, ``MAS``, ``マスター`` and friends; raise on anything else."""
    text = str(value).strip().lower()
    text = _DIFFICULTY_ALIASES.get(text, text)
    if text not in DIFFICULTIES:
        raise ValueError(f"unknown difficulty {value!r}; expected one of: {', '.join(DIFFICULTIES)}")
    return text


class ClearType(IntEnum):
    """How well a chart went, ordered so ``>=`` expresses "at least this good"."""

    NOT_CLEARED = 0
    CLEAR = 1
    FULL_COMBO = 2
    ALL_PERFECT = 3

    @property
    def code(self) -> str:
        return _CLEAR_CODES[self]

    @property
    def label(self) -> str:
        return _CLEAR_LABELS[self]

    @classmethod
    def parse(cls, value: Any) -> "ClearType":
        """Accept codes, Japanese words, common abbreviations or the raw number."""
        if isinstance(value, ClearType):
            return value
        if isinstance(value, bool):
            return cls.CLEAR if value else cls.NOT_CLEARED
        if isinstance(value, int):
            return cls(value)
        text = str(value).strip().lower().replace("-", "_").replace(" ", "")
        if text.isdigit():
            return cls(int(text))
        try:
            return _CLEAR_ALIASES[text]
        except KeyError:
            known = ", ".join(sorted({c.code for c in cls}))
            raise ValueError(f"unknown clear type {value!r}; expected one of: {known}") from None


_CLEAR_CODES = {
    ClearType.NOT_CLEARED: "not_cleared",
    ClearType.CLEAR: "clear",
    ClearType.FULL_COMBO: "full_combo",
    ClearType.ALL_PERFECT: "all_perfect",
}

_CLEAR_LABELS = {
    ClearType.NOT_CLEARED: "未クリア",
    ClearType.CLEAR: "クリア",
    ClearType.FULL_COMBO: "フルコンボ",
    ClearType.ALL_PERFECT: "オールパーフェクト",
}

_CLEAR_ALIASES: Dict[str, ClearType] = {
    "not_cleared": ClearType.NOT_CLEARED,
    "notcleared": ClearType.NOT_CLEARED,
    "none": ClearType.NOT_CLEARED,
    "failed": ClearType.NOT_CLEARED,
    "未クリア": ClearType.NOT_CLEARED,
    "未プレイ": ClearType.NOT_CLEARED,
    "clear": ClearType.CLEAR,
    "cleared": ClearType.CLEAR,
    "c": ClearType.CLEAR,
    "クリア": ClearType.CLEAR,
    "full_combo": ClearType.FULL_COMBO,
    "fullcombo": ClearType.FULL_COMBO,
    "fc": ClearType.FULL_COMBO,
    "フルコン": ClearType.FULL_COMBO,
    "フルコンボ": ClearType.FULL_COMBO,
    "all_perfect": ClearType.ALL_PERFECT,
    "allperfect": ClearType.ALL_PERFECT,
    "ap": ClearType.ALL_PERFECT,
    "オールパーフェクト": ClearType.ALL_PERFECT,
    "パフェ": ClearType.ALL_PERFECT,
}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class PlayRecord:
    """One chart of one song, as you have played it."""

    music_id: int
    difficulty: str
    clear: ClearType = ClearType.NOT_CLEARED
    score: Optional[int] = None
    updated_at: str = field(default_factory=_now)

    @property
    def key(self) -> str:
        return f"{self.music_id}:{self.difficulty}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "music_id": self.music_id,
            "difficulty": self.difficulty,
            "clear": self.clear.code,
            "score": self.score,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "PlayRecord":
        score = raw.get("score")
        return cls(
            music_id=int(raw["music_id"]),
            difficulty=parse_difficulty(raw["difficulty"]),
            clear=ClearType.parse(raw.get("clear", 0)),
            score=int(score) if score not in (None, "") else None,
            updated_at=str(raw.get("updated_at") or _now()),
        )


@dataclass(frozen=True)
class OwnedCard:
    """A card you own, with the upgrades the app shows on it."""

    card_id: int
    level: Optional[int] = None
    master_rank: int = 0
    special_training: bool = False
    updated_at: str = field(default_factory=_now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "card_id": self.card_id,
            "level": self.level,
            "master_rank": self.master_rank,
            "special_training": self.special_training,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "OwnedCard":
        level = raw.get("level")
        return cls(
            card_id=int(raw["card_id"]),
            level=int(level) if level not in (None, "") else None,
            master_rank=int(raw.get("master_rank", 0) or 0),
            special_training=bool(raw.get("special_training", False)),
            updated_at=str(raw.get("updated_at") or _now()),
        )


@dataclass(frozen=True)
class PlayerProfile:
    """Who you are in the game, as printed on the app's profile screen."""

    name: str = ""
    user_id: str = ""
    rank: Optional[int] = None
    updated_at: str = field(default_factory=_now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "user_id": self.user_id,
            "rank": self.rank,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "PlayerProfile":
        rank = raw.get("rank")
        return cls(
            name=str(raw.get("name", "")),
            user_id=str(raw.get("user_id", "")),
            rank=int(rank) if rank not in (None, "") else None,
            updated_at=str(raw.get("updated_at") or _now()),
        )
