"""Command line interface: ``python -m proseka ...`` or ``proseka ...``."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, List, Optional, Sequence

from . import __version__
from .client import DEFAULT_TTL, ProsekaClient
from .errors import ProsekaError
from .models import Card, Character, Event, Music, Unit
from .regions import DEFAULT_REGION, REGIONS

__all__ = ["main", "build_parser"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="proseka",
        description="Project SEKAI のマスターデータを取得・検索します。",
    )
    parser.add_argument("--version", action="version", version=f"proseka {__version__}")
    parser.add_argument(
        "--region", default=DEFAULT_REGION, choices=sorted(REGIONS), help="サーバー地域 (既定: jp)"
    )
    parser.add_argument("--cache-dir", default=None, help="キャッシュの保存先")
    parser.add_argument("--ttl", type=float, default=DEFAULT_TTL, help="キャッシュ有効秒数")
    parser.add_argument("--offline", action="store_true", help="通信せずキャッシュだけを使う")
    parser.add_argument("--refresh", action="store_true", help="キャッシュを無視して再取得する")
    parser.add_argument("--json", action="store_true", dest="as_json", help="JSON で出力する")
    parser.add_argument("-v", "--verbose", action="store_true", help="ログを表示する")

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("regions", help="利用できる地域を一覧する")

    p_sync = sub.add_parser("sync", help="マスターデータをダウンロードする")
    p_sync.add_argument("tables", nargs="*", help="取得するテーブル名 (既定: 主要テーブル)")

    p_char = sub.add_parser("character", help="キャラクターを検索する")
    p_char.add_argument("query", help="名前 (日本語・かな・英語) または ID")

    p_unit = sub.add_parser("unit", help="ユニットとメンバーを表示する")
    p_unit.add_argument("code", nargs="?", help="ユニット名またはコード (省略時は全件)")

    p_music = sub.add_parser("music", help="楽曲を検索する")
    p_music.add_argument("query", help="曲名・読み・作者名または ID")
    p_music.add_argument("--limit", type=int, default=20, help="表示件数")

    p_level = sub.add_parser("level", help="指定レベルの譜面を一覧する")
    p_level.add_argument("play_level", type=int, help="譜面レベル")
    p_level.add_argument("--difficulty", default=None, help="easy/normal/hard/expert/master/append")
    p_level.add_argument("--limit", type=int, default=30, help="表示件数")

    p_cards = sub.add_parser("cards", help="キャラクターのカードを一覧する")
    p_cards.add_argument("query", help="キャラクター名または ID")
    p_cards.add_argument("--rarity", default=None, help="4, 4*, rarity_4, birthday など")
    p_cards.add_argument("--attr", default=None, help="cool/cute/happy/mysterious/pure")
    p_cards.add_argument("--limit", type=int, default=50, help="表示件数")

    p_event = sub.add_parser("event", help="イベント情報を表示する")
    p_event.add_argument("--id", type=int, default=None, help="イベント ID")
    p_event.add_argument("--recent", type=int, default=None, help="直近 N 件を表示する")

    p_cache = sub.add_parser("cache", help="キャッシュを操作する")
    p_cache.add_argument("action", choices=["path", "clear"], help="path: 場所を表示 / clear: 削除")

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(message)s",
    )
    try:
        return _dispatch(args)
    except ProsekaError as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:  # pragma: no cover - interactive only
        return 130


def _dispatch(args: argparse.Namespace) -> int:
    if args.command == "regions":
        return _cmd_regions(args)

    client = ProsekaClient(
        args.region,
        cache_dir=args.cache_dir,
        ttl=args.ttl,
        offline=args.offline,
    )
    if args.refresh and args.command != "sync":
        client.sync()

    handlers = {
        "sync": _cmd_sync,
        "character": _cmd_character,
        "unit": _cmd_unit,
        "music": _cmd_music,
        "level": _cmd_level,
        "cards": _cmd_cards,
        "event": _cmd_event,
        "cache": _cmd_cache,
    }
    return handlers[args.command](client, args)


# --------------------------------------------------------------- subcommands


def _cmd_regions(args: argparse.Namespace) -> int:
    rows = [
        {"code": region.code, "label": region.label, "source": region.base_url}
        for region in REGIONS.values()
    ]
    if args.as_json:
        _emit(rows)
        return 0
    for row in rows:
        print(f"{row['code']:<4} {row['label']:<28} {row['source']}")
    return 0


def _cmd_sync(client: ProsekaClient, args: argparse.Namespace) -> int:
    counts = client.sync(args.tables or None)
    if args.as_json:
        _emit(counts)
        return 0
    for table, count in counts.items():
        print(f"{table:<20} {count:>6} 件")
    print(f"保存先: {client.cache.dir}")
    return 0


def _cmd_character(client: ProsekaClient, args: argparse.Namespace) -> int:
    matches = _resolve_characters(client, args.query)
    if not matches:
        print(f"該当するキャラクターが見つかりません: {args.query}", file=sys.stderr)
        return 2
    if args.as_json:
        _emit([c.raw for c in matches])
        return 0
    units = {unit.unit: unit for unit in client.units()}
    for character in matches:
        unit = units.get(character.unit)
        unit_name = unit.name if unit else character.unit
        print(f"#{character.id} {character.full_name} ({character.full_name_ruby})")
        print(f"  英語名   : {character.full_name_english}")
        print(f"  ユニット : {unit_name}")
        if character.height:
            print(f"  身長     : {character.height:g} cm")
        print(f"  カード数 : {len(client.cards_for_character(character))} 枚")
    return 0


def _cmd_unit(client: ProsekaClient, args: argparse.Namespace) -> int:
    units: List[Unit]
    if args.code:
        found = client.unit(args.code)
        if found is None:
            print(f"該当するユニットが見つかりません: {args.code}", file=sys.stderr)
            return 2
        units = [found]
    else:
        units = sorted(client.units(), key=lambda u: u.seq)
    if args.as_json:
        _emit([u.raw for u in units])
        return 0
    for unit in units:
        members = client.characters_in_unit(unit.unit)
        print(f"{unit.name} [{unit.unit}] {unit.color_code}")
        for member in members:
            print(f"  - {member.full_name} (#{member.id})")
    return 0


def _cmd_music(client: ProsekaClient, args: argparse.Namespace) -> int:
    matches = _resolve_musics(client, args.query)
    if not matches:
        print(f"該当する楽曲が見つかりません: {args.query}", file=sys.stderr)
        return 2
    shown = matches[: max(1, args.limit)]
    if args.as_json:
        _emit([m.raw for m in shown])
        return 0
    for music in shown:
        charts = client.difficulties_for(music.id)
        levels = " ".join(f"{c.difficulty[:2].upper()}{c.play_level}" for c in charts)
        print(f"#{music.id} {music.title}")
        print(f"  制作   : {music.credit}")
        print(f"  配信日 : {_date(music.published_at)}")
        if levels:
            print(f"  譜面   : {levels}")
    if len(matches) > len(shown):
        print(f"... 他 {len(matches) - len(shown)} 件")
    return 0


def _cmd_level(client: ProsekaClient, args: argparse.Namespace) -> int:
    pairs = client.charts_at_level(args.play_level, args.difficulty)
    if not pairs:
        print("該当する譜面がありません", file=sys.stderr)
        return 2
    shown = pairs[: max(1, args.limit)]
    if args.as_json:
        _emit([{"music": m.raw, "difficulty": d.raw} for m, d in shown])
        return 0
    for music, chart in shown:
        print(f"{chart.label:<10} {music.title}  ({chart.total_note_count} notes)")
    if len(pairs) > len(shown):
        print(f"... 他 {len(pairs) - len(shown)} 件")
    return 0


def _cmd_cards(client: ProsekaClient, args: argparse.Namespace) -> int:
    matches = _resolve_characters(client, args.query)
    if not matches:
        print(f"該当するキャラクターが見つかりません: {args.query}", file=sys.stderr)
        return 2
    character = matches[0]
    cards: List[Card] = client.cards_for_character(character, rarity=args.rarity, attr=args.attr)
    if args.as_json:
        _emit([c.raw for c in cards])
        return 0
    print(f"{character.full_name} のカード: {len(cards)} 枚")
    for card in cards[: max(1, args.limit)]:
        print(f"  #{card.id:<5} {card.rarity_stars:<5} {card.attr:<10} {card.prefix}")
    if len(cards) > args.limit:
        print(f"  ... 他 {len(cards) - args.limit} 件")
    return 0


def _cmd_event(client: ProsekaClient, args: argparse.Namespace) -> int:
    if args.id is not None:
        event = client.event(args.id)
        events = [event] if event else []
    elif args.recent:
        events = client.recent_events(args.recent)
    else:
        events = [e for e in (client.current_event(), client.next_event()) if e]
    if not events:
        print("該当するイベントがありません", file=sys.stderr)
        return 2
    if args.as_json:
        _emit([e.raw for e in events])
        return 0
    now = datetime.now(timezone.utc)
    for event in events:
        state = "開催中" if event.is_running(now) else ("開催予定" if _future(event, now) else "終了")
        print(f"#{event.id} {event.name} [{event.event_type}] {state}")
        print(f"  期間 : {_date(event.start_at)} 〜 {_date(event.aggregate_at)}")
    return 0


def _cmd_cache(client: ProsekaClient, args: argparse.Namespace) -> int:
    if args.action == "path":
        print(client.cache.dir)
        return 0
    removed = client.clear_cache()
    print(f"{removed} 件のキャッシュを削除しました")
    return 0


# ------------------------------------------------------------------ helpers


def _resolve_characters(client: ProsekaClient, query: str) -> List[Character]:
    if query.isdigit():
        found = client.character(int(query))
        return [found] if found else []
    return client.find_characters(query)


def _resolve_musics(client: ProsekaClient, query: str) -> List[Music]:
    if query.isdigit():
        found = client.music(int(query))
        if found:
            return [found]
    return client.find_musics(query)


def _future(event: Event, now: datetime) -> bool:
    return bool(event.start_at and event.start_at > now)


def _date(moment: Optional[datetime]) -> str:
    return moment.strftime("%Y-%m-%d %H:%M UTC") if moment else "-"


def _emit(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
