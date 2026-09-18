"""Local storage for your own play data, as a single readable JSON file."""

from __future__ import annotations

import csv
import io
import json
import os
from pathlib import Path
from typing import Callable, Dict, Iterable, Iterator, List, Optional

from .cache import atomic_write_text
from .errors import ProsekaError
from .play import ClearType, OwnedCard, PlayerProfile, PlayRecord, parse_difficulty

__all__ = ["PlayerStore", "default_data_dir", "parse_play_csv", "write_play_csv", "SCHEMA_VERSION"]

SCHEMA_VERSION = 1


def default_data_dir() -> Path:
    """Where play data lives: ``PROSEKA_DATA_DIR``, else ``XDG_DATA_HOME``, else ``~/.local/share``."""
    override = os.environ.get("PROSEKA_DATA_DIR")
    if override:
        return Path(override).expanduser()
    xdg = os.environ.get("XDG_DATA_HOME")
    root = Path(xdg).expanduser() if xdg else Path.home() / ".local" / "share"
    return root / "proseka"


class PlayerStore:
    """Your profile, chart records and owned cards for one region.

    Nothing here is downloaded. You enter it, or import it from a CSV you
    typed while looking at the app.
    """

    def __init__(self, path: Path, region: str = "jp") -> None:
        self.path = Path(path)
        self.region = region
        self.profile = PlayerProfile()
        self.records: Dict[str, PlayRecord] = {}
        self.cards: Dict[int, OwnedCard] = {}

    # ------------------------------------------------------------- lifecycle

    @classmethod
    def open(cls, region: str = "jp", data_dir: Optional[Path] = None) -> "PlayerStore":
        """Load the store for a region, or start an empty one if it does not exist."""
        root = Path(data_dir) if data_dir else default_data_dir()
        store = cls(root / region / "player.json", region)
        store.load()
        return store

    def load(self) -> "PlayerStore":
        if not self.path.is_file():
            return self
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ProsekaError(f"could not read play data at {self.path}: {exc}") from exc
        version = int(raw.get("version", SCHEMA_VERSION))
        if version > SCHEMA_VERSION:
            raise ProsekaError(
                f"{self.path} was written by a newer version of proseka "
                f"(schema {version}, this build understands {SCHEMA_VERSION})"
            )
        self.region = raw.get("region", self.region)
        self.profile = PlayerProfile.from_dict(raw.get("profile", {}))
        self.records = {}
        for row in raw.get("plays", []):
            record = PlayRecord.from_dict(row)
            self.records[record.key] = record
        self.cards = {}
        for row in raw.get("cards", []):
            card = OwnedCard.from_dict(row)
            self.cards[card.card_id] = card
        return self

    def save(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(self.path, json.dumps(self.to_dict(), ensure_ascii=False, indent=1))
        return self.path

    def to_dict(self) -> Dict[str, object]:
        return {
            "version": SCHEMA_VERSION,
            "region": self.region,
            "profile": self.profile.to_dict(),
            "plays": [record.to_dict() for record in self.sorted_records()],
            "cards": [card.to_dict() for card in self.sorted_cards()],
        }

    # ---------------------------------------------------------------- access

    def sorted_records(self) -> List[PlayRecord]:
        order = {name: index for index, name in enumerate(("easy", "normal", "hard", "expert", "master", "append"))}
        return sorted(self.records.values(), key=lambda r: (r.music_id, order.get(r.difficulty, 99)))

    def sorted_cards(self) -> List[OwnedCard]:
        return sorted(self.cards.values(), key=lambda c: c.card_id)

    def record(self, music_id: int, difficulty: str) -> Optional[PlayRecord]:
        return self.records.get(f"{int(music_id)}:{parse_difficulty(difficulty)}")

    def set_record(self, record: PlayRecord, *, keep_best: bool = True) -> PlayRecord:
        """Store a record. By default a worse result never overwrites a better one."""
        existing = self.records.get(record.key)
        if existing and keep_best:
            best_clear = max(existing.clear, record.clear)
            best_score = max(
                [value for value in (existing.score, record.score) if value is not None] or [None]
            )
            record = PlayRecord(
                music_id=record.music_id,
                difficulty=record.difficulty,
                clear=best_clear,
                score=best_score,
                updated_at=record.updated_at,
            )
        self.records[record.key] = record
        return record

    def remove_record(self, music_id: int, difficulty: str) -> bool:
        return self.records.pop(f"{int(music_id)}:{parse_difficulty(difficulty)}", None) is not None

    def set_card(self, card: OwnedCard) -> OwnedCard:
        self.cards[card.card_id] = card
        return card

    def remove_card(self, card_id: int) -> bool:
        return self.cards.pop(int(card_id), None) is not None

    def owns(self, card_id: int) -> bool:
        return int(card_id) in self.cards

    def __len__(self) -> int:
        return len(self.records)

    def __iter__(self) -> Iterator[PlayRecord]:
        return iter(self.sorted_records())


# -------------------------------------------------------------------- CSV io

_MUSIC_COLUMNS = ("music", "music_id", "song", "title", "曲", "曲名", "楽曲")
_DIFFICULTY_COLUMNS = ("difficulty", "diff", "難易度")
_CLEAR_COLUMNS = ("clear", "result", "クリア", "状態")
_SCORE_COLUMNS = ("score", "スコア")


def parse_play_csv(text: str, resolve_music: Callable[[str], int]) -> List[PlayRecord]:
    """Read a CSV of your results.

    The header must name a song column and a difficulty column; ``clear`` and
    ``score`` are optional. The song may be an id or a title, resolved by the
    ``resolve_music`` callback. Raises ``ProsekaError`` naming the offending
    line, so a typo does not silently drop a row.
    """
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ProsekaError("the CSV has no header row")
    columns = {(name or "").strip().lower(): (name or "") for name in reader.fieldnames}
    music_column = _pick(columns, _MUSIC_COLUMNS, "song")
    difficulty_column = _pick(columns, _DIFFICULTY_COLUMNS, "difficulty")
    clear_column = _optional(columns, _CLEAR_COLUMNS)
    score_column = _optional(columns, _SCORE_COLUMNS)

    records: List[PlayRecord] = []
    for line, row in enumerate(reader, start=2):
        song = (row.get(music_column) or "").strip()
        if not song:
            continue
        try:
            music_id = resolve_music(song)
            difficulty = parse_difficulty(row.get(difficulty_column) or "")
            clear = ClearType.parse(row.get(clear_column) or 0) if clear_column else ClearType.CLEAR
            raw_score = (row.get(score_column) or "").strip().replace(",", "") if score_column else ""
            score = int(raw_score) if raw_score else None
        except (ValueError, ProsekaError) as exc:
            raise ProsekaError(f"line {line}: {exc}") from exc
        records.append(
            PlayRecord(music_id=music_id, difficulty=difficulty, clear=clear, score=score)
        )
    return records


def write_play_csv(records: Iterable[PlayRecord], titles: Optional[Dict[int, str]] = None) -> str:
    """Render records back to CSV, with song titles when they are available."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["music_id", "title", "difficulty", "clear", "score"])
    for record in records:
        writer.writerow(
            [
                record.music_id,
                (titles or {}).get(record.music_id, ""),
                record.difficulty,
                record.clear.code,
                "" if record.score is None else record.score,
            ]
        )
    return buffer.getvalue()


def _pick(columns: Dict[str, str], candidates: Iterable[str], what: str) -> str:
    for candidate in candidates:
        if candidate in columns:
            return columns[candidate]
    raise ProsekaError(
        f"the CSV needs a {what} column; expected one of: {', '.join(candidates)}"
    )


def _optional(columns: Dict[str, str], candidates: Iterable[str]) -> Optional[str]:
    for candidate in candidates:
        if candidate in columns:
            return columns[candidate]
    return None
