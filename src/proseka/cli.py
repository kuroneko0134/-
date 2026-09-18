"""Command line interface: ``python -m proseka ...`` or ``proseka ...``."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional, Sequence

from . import __version__
from .client import DEFAULT_TTL, ProsekaClient
from .collection import Collection
from .errors import ProsekaError
from .models import Card, Character, Event, Music, Unit
from .play import ClearType, OwnedCard, PlayerProfile, PlayRecord, parse_difficulty
from .regions import DEFAULT_REGION, REGIONS
from .store import PlayerStore, parse_play_csv, write_play_csv

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
    parser.add_argument("--data-dir", default=None, help="自分のプレイデータの保存先")
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

    _add_me_parser(sub)

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
        "me": _cmd_me,
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


# --------------------------------------------------- 自分のプレイデータ (me)


def _add_me_parser(sub: "argparse._SubParsersAction") -> None:
    """``me`` groups everything that touches your own records."""
    p_me = sub.add_parser("me", help="スマホのアプリで見た自分の記録を扱う")
    actions = p_me.add_subparsers(dest="me_action", required=True)

    p_profile = actions.add_parser("profile", help="プロフィールを表示・登録する")
    p_profile.add_argument("--name", default=None, help="プレイヤー名")
    p_profile.add_argument("--user-id", default=None, help="ID (プロフィール画面の数字)")
    p_profile.add_argument("--rank", type=int, default=None, help="ランク")

    p_play = actions.add_parser("play", help="譜面の結果を記録する")
    p_play.add_argument("song", help="曲名または楽曲 ID")
    p_play.add_argument("difficulty", help="easy/normal/hard/expert/master/append")
    p_play.add_argument("--clear", default="clear", help="未クリア/クリア/fc/ap")
    p_play.add_argument("--score", type=int, default=None, help="スコア")
    p_play.add_argument("--overwrite", action="store_true", help="良い記録でも上書きする")
    p_play.add_argument("--remove", action="store_true", help="記録を削除する")

    p_import = actions.add_parser("import", help="CSV から結果をまとめて取り込む")
    p_import.add_argument("path", help="CSV ファイル (- で標準入力)")
    p_import.add_argument("--overwrite", action="store_true", help="良い記録でも上書きする")

    p_export = actions.add_parser("export", help="記録を書き出す")
    p_export.add_argument("--csv", action="store_true", help="CSV で出力する")

    p_progress = actions.add_parser("progress", help="難易度ごとの達成状況を表示する")
    p_progress.add_argument("--difficulty", default="master", help="対象の難易度")

    p_todo = actions.add_parser("todo", help="目標に届いていない譜面を一覧する")
    p_todo.add_argument("--goal", default="full_combo", help="clear/fc/ap")
    p_todo.add_argument("--difficulty", default="master", help="対象の難易度")
    p_todo.add_argument("--level", type=int, default=None, help="譜面レベル")
    p_todo.add_argument("--limit", type=int, default=20, help="表示件数")

    p_mark = actions.add_parser("mark", help="クリア済みの譜面をまとめて記録する")
    p_mark.add_argument("--difficulty", default="master", help="対象の難易度")
    p_mark.add_argument("--clear", default="clear", help="記録する結果 (クリア/fc/ap)")
    p_mark.add_argument("--level", type=int, default=None, help="このレベルだけ")
    p_mark.add_argument("--min-level", type=int, default=None, help="このレベル以上")
    p_mark.add_argument("--max-level", type=int, default=None, help="このレベル以下")
    p_mark.add_argument("--overwrite", action="store_true", help="良い記録も書き換える")
    p_mark.add_argument("--dry-run", action="store_true", help="保存せず対象だけ表示する")

    p_cards = actions.add_parser("cards", help="所持カードと未所持カードを比べる")
    p_cards.add_argument("character", help="キャラクター名または ID")
    p_cards.add_argument("--rarity", default=None, help="4, 4*, birthday など")

    p_card = actions.add_parser("card", help="所持カードを登録・削除する")
    p_card.add_argument("card_id", type=int, help="カード ID")
    p_card.add_argument("--level", type=int, default=None, help="カードレベル")
    p_card.add_argument("--master-rank", type=int, default=0, help="マスターランク")
    p_card.add_argument("--trained", action="store_true", help="特訓後")
    p_card.add_argument("--remove", action="store_true", help="所持カードから外す")

    p_event = actions.add_parser("event", help="イベントポイントの進捗とペースを出す")
    p_event.add_argument("--points", type=int, required=True, help="現在のポイント")
    p_event.add_argument("--target", type=int, required=True, help="目標ポイント")
    p_event.add_argument("--event-id", type=int, default=None, help="対象イベント (既定: 開催中)")


def _cmd_me(client: ProsekaClient, args: argparse.Namespace) -> int:
    store = PlayerStore.open(args.region, data_dir=args.data_dir)
    collection = Collection(client, store)
    handlers = {
        "profile": _me_profile,
        "play": _me_play,
        "import": _me_import,
        "export": _me_export,
        "progress": _me_progress,
        "todo": _me_todo,
        "mark": _me_mark,
        "cards": _me_cards,
        "card": _me_card,
        "event": _me_event,
    }
    return handlers[args.me_action](collection, args)


def _me_profile(collection: Collection, args: argparse.Namespace) -> int:
    store = collection.store
    if any(value is not None for value in (args.name, args.user_id, args.rank)):
        current = store.profile
        store.profile = PlayerProfile(
            name=args.name if args.name is not None else current.name,
            user_id=args.user_id if args.user_id is not None else current.user_id,
            rank=args.rank if args.rank is not None else current.rank,
        )
        store.save()
    profile = store.profile
    if args.as_json:
        _emit(profile.to_dict())
        return 0
    print(f"プレイヤー : {profile.name or '(未設定)'}")
    print(f"ID         : {profile.user_id or '(未設定)'}")
    print(f"ランク     : {profile.rank if profile.rank is not None else '(未設定)'}")
    print(f"記録       : {len(store)} 譜面 / 所持カード {len(store.cards)} 枚")
    print(f"保存先     : {store.path}")
    return 0


def _me_play(collection: Collection, args: argparse.Namespace) -> int:
    try:
        music_id = collection.resolve_music_id(args.song)
        difficulty = parse_difficulty(args.difficulty)
    except ValueError as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 2
    store = collection.store
    music = collection.client.music(music_id)

    if args.remove:
        removed = store.remove_record(music_id, difficulty)
        store.save()
        print(f"{'削除しました' if removed else '記録がありません'}: {music.title} [{difficulty}]")
        return 0 if removed else 2

    try:
        clear = ClearType.parse(args.clear)
    except ValueError as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 2
    saved = store.set_record(
        PlayRecord(music_id=music_id, difficulty=difficulty, clear=clear, score=args.score),
        keep_best=not args.overwrite,
    )
    store.save()
    if args.as_json:
        _emit(saved.to_dict())
        return 0
    score = f" / {saved.score:,} 点" if saved.score is not None else ""
    print(f"記録しました: {music.title} [{difficulty}] {saved.clear.label}{score}")
    return 0


def _me_import(collection: Collection, args: argparse.Namespace) -> int:
    text = sys.stdin.read() if args.path == "-" else Path(args.path).read_text(encoding="utf-8")
    records = parse_play_csv(text, collection.resolve_music_id)
    store = collection.store
    for record in records:
        store.set_record(record, keep_best=not args.overwrite)
    store.save()
    if args.as_json:
        _emit({"imported": len(records), "total": len(store)})
        return 0
    print(f"{len(records)} 件を取り込みました (記録は合計 {len(store)} 譜面)")
    return 0


def _me_export(collection: Collection, args: argparse.Namespace) -> int:
    store = collection.store
    records = store.sorted_records()
    if args.csv:
        sys.stdout.write(write_play_csv(records, collection.titles(records)))
        return 0
    _emit(store.to_dict())
    return 0


def _me_progress(collection: Collection, args: argparse.Namespace) -> int:
    summaries = collection.level_summary(args.difficulty)
    if not summaries:
        print("対象の譜面がありません", file=sys.stderr)
        return 2
    if args.as_json:
        _emit(
            [
                {
                    "level": s.level,
                    "total": s.total,
                    "cleared": s.cleared,
                    "full_combo": s.full_combo,
                    "all_perfect": s.all_perfect,
                }
                for s in summaries
            ]
        )
        return 0
    print(f"{args.difficulty.upper()} の達成状況")
    print(f"{'Lv':>3}  {'曲数':>4}  {'クリア':>8}  {'フルコン':>8}  {'AP':>8}")
    for summary in summaries:
        print(
            f"{summary.level:>3}  {summary.total:>4}  "
            f"{summary.cleared:>4} ({summary.rate(ClearType.CLEAR):>4.0%})  "
            f"{summary.full_combo:>4} ({summary.rate(ClearType.FULL_COMBO):>4.0%})  "
            f"{summary.all_perfect:>4} ({summary.rate(ClearType.ALL_PERFECT):>4.0%})"
        )
    return 0


def _me_todo(collection: Collection, args: argparse.Namespace) -> int:
    try:
        goal = ClearType.parse(args.goal)
    except ValueError as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 2
    rows = collection.todo(goal, difficulty=args.difficulty, level=args.level)
    if not rows:
        print("すべて達成済みです")
        return 0
    if args.as_json:
        _emit(
            [
                {
                    "music_id": row.music.id,
                    "title": row.music.title,
                    "difficulty": row.chart.difficulty,
                    "play_level": row.chart.play_level,
                    "clear": row.clear.code,
                }
                for row in rows[: max(1, args.limit)]
            ]
        )
        return 0
    print(f"{goal.label}まで残り {len(rows)} 譜面")
    for row in rows[: max(1, args.limit)]:
        print(f"  {row.chart.label:<10} {row.clear.label:<10} {row.music.title}")
    if len(rows) > args.limit:
        print(f"  ... 他 {len(rows) - args.limit} 件")
    return 0


def _me_mark(collection: Collection, args: argparse.Namespace) -> int:
    """Bulk-record play you have already done. It does not play anything."""
    try:
        result = collection.mark_all(
            args.clear,
            difficulty=args.difficulty,
            level=args.level,
            min_level=args.min_level,
            max_level=args.max_level,
            overwrite=args.overwrite,
            dry_run=args.dry_run,
        )
    except ValueError as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 2
    if not result.total:
        print("対象の譜面がありません", file=sys.stderr)
        return 2
    if not args.dry_run:
        collection.store.save()
    if args.as_json:
        _emit(
            {
                "clear": result.clear.code,
                "total": result.total,
                "changed": result.changed_count,
                "unchanged": result.unchanged_count,
                "dry_run": result.dry_run,
                "charts": [
                    {
                        "music_id": row.music.id,
                        "title": row.music.title,
                        "difficulty": row.chart.difficulty,
                        "play_level": row.chart.play_level,
                    }
                    for row in result.changed
                ],
            }
        )
        return 0
    verb = "記録する予定" if result.dry_run else "記録しました"
    print(f"{args.difficulty.upper()} {result.total} 譜面のうち {result.changed_count} 件を{verb} ({result.clear.label})")
    for row in result.changed[:5]:
        print(f"  {row.chart.label:<10} {row.music.title}")
    if result.changed_count > 5:
        print(f"  ... 他 {result.changed_count - 5} 件")
    if result.unchanged_count:
        print(f"  すでに同等以上: {result.unchanged_count} 件")
    if result.dry_run:
        print("  --dry-run のため保存していません")
    return 0


def _me_cards(collection: Collection, args: argparse.Namespace) -> int:
    matches = _resolve_characters(collection.client, args.character)
    if not matches:
        print(f"該当するキャラクターが見つかりません: {args.character}", file=sys.stderr)
        return 2
    character = matches[0]
    owned, missing = collection.card_collection(character, rarity=args.rarity)
    if args.as_json:
        _emit({"owned": [c.raw for c in owned], "missing": [c.raw for c in missing]})
        return 0
    total = len(owned) + len(missing)
    print(f"{character.full_name}: {len(owned)} / {total} 枚")
    for card in owned:
        print(f"  ○ #{card.id:<5} {card.rarity_stars:<5} {card.prefix}")
    for card in missing:
        print(f"  ・#{card.id:<5} {card.rarity_stars:<5} {card.prefix}")
    return 0


def _me_card(collection: Collection, args: argparse.Namespace) -> int:
    store = collection.store
    card = collection.client.card(args.card_id)
    if card is None:
        print(f"カード #{args.card_id} はマスターデータにありません", file=sys.stderr)
        return 2
    if args.remove:
        removed = store.remove_card(args.card_id)
        store.save()
        print(f"{'外しました' if removed else '所持していません'}: #{card.id} {card.prefix}")
        return 0 if removed else 2
    store.set_card(
        OwnedCard(
            card_id=card.id,
            level=args.level,
            master_rank=args.master_rank,
            special_training=args.trained,
        )
    )
    store.save()
    print(f"登録しました: #{card.id} {card.rarity_stars} {card.prefix}")
    return 0


def _me_event(collection: Collection, args: argparse.Namespace) -> int:
    event = collection.client.event(args.event_id) if args.event_id else None
    if args.event_id and event is None:
        print(f"イベント #{args.event_id} が見つかりません", file=sys.stderr)
        return 2
    pace = collection.event_pace(args.points, args.target, event=event)
    if pace is None:
        print("開催中のイベントがありません", file=sys.stderr)
        return 2
    if args.as_json:
        _emit(
            {
                "event": pace.event.name,
                "points": pace.points,
                "target": pace.target,
                "remaining": pace.remaining,
                "hours_left": round(pace.hours_left, 2),
                "points_per_hour": None if pace.points_per_hour is None else round(pace.points_per_hour),
            }
        )
        return 0
    print(f"{pace.event.name} ({_date(pace.event.start_at)} 〜 {_date(pace.ends_at)})")
    print(f"  現在     : {pace.points:,} pt")
    print(f"  目標     : {pace.target:,} pt")
    if pace.reached:
        print("  達成済みです")
        return 0
    print(f"  残り     : {pace.remaining:,} pt / {pace.hours_left:.1f} 時間")
    per_hour = pace.points_per_hour
    if per_hour is None:
        print("  集計が終了しているため間に合いません")
    else:
        print(f"  必要ペース: {per_hour:,.0f} pt/時")
    return 0
