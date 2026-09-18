from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from proseka.cli import main

from support import seed_cache


class CliTestCase(unittest.TestCase):
    """Every command runs against a seeded cache in offline mode, so no network."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        seed_cache(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        argv = ["--offline", "--cache-dir", self.tmp.name, *args]
        with redirect_stdout(out), redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue(), err.getvalue()


class RegionsCommandTests(CliTestCase):
    def test_lists_every_region(self):
        code, out, _ = self.run_cli("regions")
        self.assertEqual(code, 0)
        for region in ("jp", "en", "tc", "kr", "cn"):
            self.assertIn(region, out)

    def test_json_output_is_machine_readable(self):
        _, out, _ = self.run_cli("--json", "regions")
        rows = json.loads(out)
        self.assertEqual(rows[0]["code"], "jp")


class CharacterCommandTests(CliTestCase):
    def test_search_by_name(self):
        code, out, _ = self.run_cli("character", "一歌")
        self.assertEqual(code, 0)
        self.assertIn("星乃 一歌", out)
        self.assertIn("Leo/need", out)

    def test_search_by_id(self):
        _, out, _ = self.run_cli("character", "21")
        self.assertIn("初音 ミク", out)

    def test_json_output_returns_raw_records(self):
        _, out, _ = self.run_cli("--json", "character", "1")
        self.assertEqual(json.loads(out)[0]["modelName"], "01ichika")

    def test_no_match_exits_with_code_two(self):
        code, _, err = self.run_cli("character", "存在しない人")
        self.assertEqual(code, 2)
        self.assertIn("見つかりません", err)


class UnitCommandTests(CliTestCase):
    def test_single_unit_lists_its_members(self):
        code, out, _ = self.run_cli("unit", "Leo/need")
        self.assertEqual(code, 0)
        self.assertIn("星乃 一歌", out)
        self.assertIn("天馬 咲希", out)

    def test_without_an_argument_every_unit_is_listed(self):
        _, out, _ = self.run_cli("unit")
        self.assertIn("Leo/need", out)
        self.assertIn("バーチャル・シンガー", out)

    def test_unknown_unit_exits_with_code_two(self):
        code, _, _ = self.run_cli("unit", "架空バンド")
        self.assertEqual(code, 2)


class MusicCommandTests(CliTestCase):
    def test_search_shows_credits_and_charts(self):
        code, out, _ = self.run_cli("music", "Tell Your World")
        self.assertEqual(code, 0)
        self.assertIn("kz", out)
        self.assertIn("MA", out)

    def test_limit_is_respected(self):
        _, out, _ = self.run_cli("--json", "music", "kz", "--limit", "1")
        self.assertEqual(len(json.loads(out)), 1)

    def test_no_match_exits_with_code_two(self):
        code, _, _ = self.run_cli("music", "この曲は存在しない")
        self.assertEqual(code, 2)


class LevelCommandTests(CliTestCase):
    def test_lists_charts_at_a_level(self):
        code, out, _ = self.run_cli("level", "26", "--difficulty", "master")
        self.assertEqual(code, 0)
        self.assertIn("MASTER 26", out)

    def test_unused_level_exits_with_code_two(self):
        code, _, _ = self.run_cli("level", "99")
        self.assertEqual(code, 2)


class CardsCommandTests(CliTestCase):
    def test_lists_cards_for_a_character(self):
        code, out, _ = self.run_cli("cards", "一歌")
        self.assertEqual(code, 0)
        self.assertIn("星乃 一歌 のカード", out)

    def test_rarity_filter_narrows_the_list(self):
        _, everything, _ = self.run_cli("--json", "cards", "1")
        _, four_star, _ = self.run_cli("--json", "cards", "1", "--rarity", "4")
        self.assertLess(len(json.loads(four_star)), len(json.loads(everything)))
        self.assertTrue(all(c["cardRarityType"] == "rarity_4" for c in json.loads(four_star)))

    def test_unknown_character_exits_with_code_two(self):
        code, _, _ = self.run_cli("cards", "誰でもない")
        self.assertEqual(code, 2)


class EventCommandTests(CliTestCase):
    def test_event_by_id(self):
        code, out, _ = self.run_cli("event", "--id", "1")
        self.assertEqual(code, 0)
        self.assertIn("雨上がりの一番星", out)
        self.assertIn("終了", out)

    def test_recent_events(self):
        _, out, _ = self.run_cli("--json", "event", "--recent", "2")
        self.assertEqual(len(json.loads(out)), 2)

    def test_missing_event_exits_with_code_two(self):
        code, _, _ = self.run_cli("event", "--id", "99999")
        self.assertEqual(code, 2)


class CacheCommandTests(CliTestCase):
    def test_path_points_at_the_region_directory(self):
        code, out, _ = self.run_cli("cache", "path")
        self.assertEqual(code, 0)
        self.assertIn("jp", out.strip())

    def test_clear_reports_the_number_of_files_removed(self):
        _, out, _ = self.run_cli("cache", "clear")
        self.assertIn("6 件", out)
        code, _, err = self.run_cli("character", "一歌")
        self.assertEqual(code, 1)
        self.assertIn("エラー", err)


class OfflineWithoutCacheTests(unittest.TestCase):
    def test_a_missing_cache_reports_an_error_not_a_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            err = io.StringIO()
            with redirect_stderr(err), redirect_stdout(io.StringIO()):
                code = main(["--offline", "--cache-dir", tmp, "character", "1"])
        self.assertEqual(code, 1)
        self.assertIn("エラー", err.getvalue())


if __name__ == "__main__":
    unittest.main()
