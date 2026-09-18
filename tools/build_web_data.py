#!/usr/bin/env python3
"""Build the compact chart dataset the web app ships with.

Usage: python3 tools/build_web_data.py [--region jp] [--out web/data/charts.json]

The app runs entirely in the browser, so every song and chart it needs is
baked into one small JSON file instead of being fetched at view time.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from proseka import ProsekaClient  # noqa: E402
from proseka.play import DIFFICULTIES  # noqa: E402


def build(region: str, cache_dir: str | None = None, offline: bool = False) -> dict:
    client = ProsekaClient(region, cache_dir=cache_dir, offline=offline)
    charts: dict[int, list[list[int]]] = {}
    for chart in client.music_difficulties():
        if chart.difficulty not in DIFFICULTIES:
            continue
        charts.setdefault(chart.music_id, []).append(
            [DIFFICULTIES.index(chart.difficulty), chart.play_level, chart.total_note_count]
        )

    songs = []
    for music in sorted(client.musics(), key=lambda m: m.id):
        rows = charts.get(music.id)
        if not rows:
            continue
        rows.sort()
        songs.append(
            {
                "i": music.id,
                "t": music.title,
                "r": music.pronunciation,
                "c": music.credit,
                "d": rows,
            }
        )

    return {
        "version": 1,
        "region": region,
        "generatedAt": date.today().isoformat(),
        "difficulties": list(DIFFICULTIES),
        "songs": songs,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", default="jp")
    parser.add_argument("--cache-dir", default=None)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--out", default=str(ROOT / "web" / "data" / "charts.json"))
    args = parser.parse_args()

    payload = build(args.region, args.cache_dir, args.offline)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    charts = sum(len(song["d"]) for song in payload["songs"])
    print(f"{len(payload['songs'])} 曲 / {charts} 譜面 -> {out} ({out.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
