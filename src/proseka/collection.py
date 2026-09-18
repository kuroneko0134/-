"""Join your own play data with the master data.

This is where the two halves meet: the app on your phone tells you what you
have done, the master data says what exists, and the difference is the useful
part.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence, Tuple, Union

from .client import ProsekaClient
from .models import Card, Character, Event, Music, MusicDifficulty
from .play import ClearType, PlayRecord, parse_difficulty
from .store import PlayerStore

__all__ = ["Collection", "ChartProgress", "LevelSummary", "EventPace"]


@dataclass(frozen=True)
class ChartProgress:
    """One chart together with your result on it, if you have one."""

    music: Music
    chart: MusicDifficulty
    record: Optional[PlayRecord] = None

    @property
    def clear(self) -> ClearType:
        return self.record.clear if self.record else ClearType.NOT_CLEARED

    @property
    def score(self) -> Optional[int]:
        return self.record.score if self.record else None

    def reached(self, goal: ClearType) -> bool:
        return self.clear >= goal


@dataclass(frozen=True)
class LevelSummary:
    """How far you have got with every chart of one level."""

    level: int
    total: int
    cleared: int
    full_combo: int
    all_perfect: int

    @property
    def remaining(self) -> int:
        return self.total - self.cleared

    def rate(self, goal: ClearType = ClearType.CLEAR) -> float:
        """Share of charts at this level that reached ``goal``, from 0.0 to 1.0."""
        if not self.total:
            return 0.0
        done = {
            ClearType.CLEAR: self.cleared,
            ClearType.FULL_COMBO: self.full_combo,
            ClearType.ALL_PERFECT: self.all_perfect,
        }.get(goal, self.cleared)
        return done / self.total


@dataclass(frozen=True)
class EventPace:
    """What the current event still asks of you."""

    event: Event
    points: int
    target: int
    now: datetime

    @property
    def remaining(self) -> int:
        return max(0, self.target - self.points)

    @property
    def ends_at(self) -> Optional[datetime]:
        return self.event.aggregate_at or self.event.closed_at

    @property
    def hours_left(self) -> float:
        end = self.ends_at
        if end is None:
            return 0.0
        return max(0.0, (end - self.now).total_seconds() / 3600.0)

    @property
    def points_per_hour(self) -> Optional[float]:
        """Points you still need every hour. ``None`` when the event is over."""
        if self.remaining == 0:
            return 0.0
        hours = self.hours_left
        return None if hours <= 0 else self.remaining / hours

    @property
    def reached(self) -> bool:
        return self.points >= self.target


class Collection:
    """Answers questions that need both the master data and your own records."""

    def __init__(self, client: ProsekaClient, store: PlayerStore) -> None:
        self.client = client
        self.store = store

    # --------------------------------------------------------------- charts

    def chart_progress(
        self,
        *,
        difficulty: Optional[str] = None,
        level: Optional[int] = None,
        music_id: Optional[int] = None,
    ) -> List[ChartProgress]:
        """Every chart matching the filters, each paired with your result."""
        wanted = parse_difficulty(difficulty) if difficulty else None
        musics = {music.id: music for music in self.client.musics()}
        rows: List[ChartProgress] = []
        for chart in self.client.music_difficulties():
            if wanted and chart.difficulty != wanted:
                continue
            if level is not None and chart.play_level != int(level):
                continue
            if music_id is not None and chart.music_id != int(music_id):
                continue
            music = musics.get(chart.music_id)
            if music is None:
                continue
            rows.append(
                ChartProgress(music=music, chart=chart, record=self.store.record(music.id, chart.difficulty))
            )
        rows.sort(key=lambda row: (row.chart.play_level, row.music.id))
        return rows

    def todo(
        self,
        goal: Union[ClearType, str] = ClearType.FULL_COMBO,
        *,
        difficulty: Optional[str] = None,
        level: Optional[int] = None,
    ) -> List[ChartProgress]:
        """Charts that have not reached the goal yet, closest to it first."""
        wanted = ClearType.parse(goal)
        rows = [row for row in self.chart_progress(difficulty=difficulty, level=level) if not row.reached(wanted)]
        rows.sort(key=lambda row: (-int(row.clear), row.chart.play_level, row.music.id))
        return rows

    def level_summary(self, difficulty: str = "master") -> List[LevelSummary]:
        """Per-level progress for one difficulty, lowest level first."""
        buckets: Dict[int, List[ChartProgress]] = {}
        for row in self.chart_progress(difficulty=difficulty):
            buckets.setdefault(row.chart.play_level, []).append(row)
        summaries = []
        for level in sorted(buckets):
            rows = buckets[level]
            summaries.append(
                LevelSummary(
                    level=level,
                    total=len(rows),
                    cleared=sum(1 for row in rows if row.reached(ClearType.CLEAR)),
                    full_combo=sum(1 for row in rows if row.reached(ClearType.FULL_COMBO)),
                    all_perfect=sum(1 for row in rows if row.reached(ClearType.ALL_PERFECT)),
                )
            )
        return summaries

    def clear_counts(self, difficulty: Optional[str] = None) -> Dict[str, int]:
        """How many charts sit at each clear type, including the untouched ones."""
        counts = {clear.code: 0 for clear in ClearType}
        for row in self.chart_progress(difficulty=difficulty):
            counts[row.clear.code] += 1
        return counts

    # ---------------------------------------------------------------- cards

    def card_collection(
        self, character: Union[int, Character], *, rarity: Optional[str] = None
    ) -> Tuple[List[Card], List[Card]]:
        """Split a character's cards into the ones you own and the ones you do not."""
        cards = self.client.cards_for_character(character, rarity=rarity)
        owned = [card for card in cards if self.store.owns(card.id)]
        missing = [card for card in cards if not self.store.owns(card.id)]
        return owned, missing

    def owned_cards(self) -> List[Card]:
        """Your cards, as master-data records, newest id last."""
        by_id = {card.id: card for card in self.client.cards()}
        return [by_id[card_id] for card_id in sorted(self.store.cards) if card_id in by_id]

    def unknown_card_ids(self) -> List[int]:
        """Card ids in your store that no longer exist in the master data."""
        known = {card.id for card in self.client.cards()}
        return sorted(card_id for card_id in self.store.cards if card_id not in known)

    # --------------------------------------------------------------- events

    def event_pace(
        self,
        points: int,
        target: int,
        *,
        event: Optional[Event] = None,
        now: Optional[datetime] = None,
    ) -> Optional[EventPace]:
        """Work out the pace needed to hit a point target before the event closes."""
        moment = now or datetime.now(timezone.utc)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        running = event or self.client.current_event(moment)
        if running is None:
            return None
        return EventPace(event=running, points=int(points), target=int(target), now=moment)

    # -------------------------------------------------------------- helpers

    def resolve_music_id(self, text: str) -> int:
        """Turn an id or a title into a music id, raising when it is ambiguous."""
        text = str(text).strip()
        if text.isdigit() and self.client.music(int(text)):
            return int(text)
        matches = self.client.find_musics(text)
        if not matches:
            raise ValueError(f"no song matches {text!r}")
        exact = [music for music in matches if music.title.strip().lower() == text.lower()]
        if exact:
            return exact[0].id
        if len(matches) > 1:
            names = ", ".join(music.title for music in matches[:5])
            raise ValueError(f"{text!r} matches {len(matches)} songs ({names}); use the song id")
        return matches[0].id

    def titles(self, records: Sequence[PlayRecord]) -> Dict[int, str]:
        by_id = {music.id: music.title for music in self.client.musics()}
        return {record.music_id: by_id.get(record.music_id, "") for record in records}
