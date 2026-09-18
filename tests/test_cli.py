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
        argv = [
            "--offline",
            "--cache-dir", self.tmp.name,
            "--data-dir", str(Path(self.tmp.name) / "mydata"),
            *args,
        ]
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


class MeProfileCommandTests(CliTestCase):
    def test_setting_and_reading_back_a_profile(self):
        code, _, _ = self.run_cli("me", "profile", "--name", "くろねこ", "--user-id", "1234", "--rank", "120")
        self.assertEqual(code, 0)
        _, out, _ = self.run_cli("me", "profile")
        self.assertIn("くろねこ", out)
        self.assertIn("1234", out)
        self.assertIn("120", out)

    def test_an_empty_profile_says_so_rather_than_failing(self):
        code, out, _ = self.run_cli("me", "profile")
        self.assertEqual(code, 0)
        self.assertIn("未設定", out)

    def test_a_single_field_can_be_updated_without_clearing_the_others(self):
        self.run_cli("me", "profile", "--name", "くろねこ", "--user-id", "1234")
        self.run_cli("me", "profile", "--rank", "130")
        _, out, _ = self.run_cli("--json", "me", "profile")
        profile = json.loads(out)
        self.assertEqual((profile["name"], profile["user_id"], profile["rank"]), ("くろねこ", "1234", 130))


class MePlayCommandTests(CliTestCase):
    def test_recording_a_result_by_title(self):
        code, out, _ = self.run_cli("me", "play", "テオ", "master", "--clear", "fc", "--score", "1180000")
        self.assertEqual(code, 0)
        self.assertIn("フルコンボ", out)
        self.assertIn("1,180,000", out)

    def test_japanese_difficulty_and_clear_names(self):
        code, out, _ = self.run_cli("me", "play", "ロキ", "マスター", "--clear", "クリア")
        self.assertEqual(code, 0)
        self.assertIn("クリア", out)

    def test_a_worse_result_does_not_replace_a_better_one(self):
        self.run_cli("me", "play", "テオ", "master", "--clear", "ap")
        _, out, _ = self.run_cli("me", "play", "テオ", "master", "--clear", "clear")
        self.assertIn("オールパーフェクト", out)

    def test_overwrite_forces_the_new_result(self):
        self.run_cli("me", "play", "テオ", "master", "--clear", "ap")
        _, out, _ = self.run_cli("me", "play", "テオ", "master", "--clear", "clear", "--overwrite")
        self.assertIn("クリア", out)
        self.assertNotIn("オールパーフェクト", out)

    def test_removing_a_record(self):
        self.run_cli("me", "play", "テオ", "master", "--clear", "fc")
        code, out, _ = self.run_cli("me", "play", "テオ", "master", "--remove")
        self.assertEqual(code, 0)
        self.assertIn("削除しました", out)
        code, _, _ = self.run_cli("me", "play", "テオ", "master", "--remove")
        self.assertEqual(code, 2)

    def test_an_unknown_song_exits_with_code_two(self):
        code, _, err = self.run_cli("me", "play", "存在しない曲", "master")
        self.assertEqual(code, 2)
        self.assertIn("エラー", err)

    def test_an_unknown_difficulty_exits_with_code_two(self):
        code, _, _ = self.run_cli("me", "play", "テオ", "lunatic")
        self.assertEqual(code, 2)

    def test_an_unknown_clear_type_exits_with_code_two(self):
        code, _, _ = self.run_cli("me", "play", "テオ", "master", "--clear", "だいたい")
        self.assertEqual(code, 2)


class MeImportExportCommandTests(CliTestCase):
    def csv_file(self, text):
        path = Path(self.tmp.name) / "plays.csv"
        path.write_text(text, encoding="utf-8")
        return str(path)

    def test_importing_a_japanese_csv(self):
        path = self.csv_file("曲名,難易度,クリア,スコア\nテオ,マスター,fc,1180000\nロキ,master,クリア,980000\n")
        code, out, _ = self.run_cli("me", "import", path)
        self.assertEqual(code, 0)
        self.assertIn("2 件", out)

    def test_imported_records_come_back_out_of_export(self):
        path = self.csv_file("music,difficulty,clear\nテオ,master,ap\n")
        self.run_cli("me", "import", path)
        _, out, _ = self.run_cli("me", "export", "--csv")
        self.assertIn("テオ", out)
        self.assertIn("all_perfect", out)

    def test_export_as_json_carries_the_schema_version(self):
        _, out, _ = self.run_cli("me", "export")
        self.assertEqual(json.loads(out)["version"], 1)

    def test_a_broken_csv_reports_the_line_and_exits_one(self):
        path = self.csv_file("music,difficulty\nテオ,lunatic\n")
        code, _, err = self.run_cli("me", "import", path)
        self.assertEqual(code, 1)
        self.assertIn("line 2", err)


class MeProgressCommandTests(CliTestCase):
    def test_progress_table_lists_every_level(self):
        self.run_cli("me", "play", "テオ", "master", "--clear", "fc")
        code, out, _ = self.run_cli("me", "progress", "--difficulty", "master")
        self.assertEqual(code, 0)
        self.assertIn("32", out)
        self.assertIn("100%", out)

    def test_progress_as_json(self):
        _, out, _ = self.run_cli("--json", "me", "progress", "--difficulty", "master")
        rows = json.loads(out)
        self.assertEqual([row["level"] for row in rows], [26, 29, 32])

    def test_todo_hides_what_is_already_done(self):
        self.run_cli("me", "play", "テオ", "master", "--clear", "fc")
        code, out, _ = self.run_cli("me", "todo", "--goal", "fc", "--difficulty", "master")
        self.assertEqual(code, 0)
        self.assertNotIn("テオ", out)
        self.assertIn("ロキ", out)

    def test_todo_is_empty_once_everything_is_cleared(self):
        for title in ("Tell Your World", "ロキ", "テオ"):
            self.run_cli("me", "play", title, "master", "--clear", "ap")
        code, out, _ = self.run_cli("me", "todo", "--goal", "ap", "--difficulty", "master")
        self.assertEqual(code, 0)
        self.assertIn("すべて達成済み", out)

    def test_todo_rejects_an_unknown_goal(self):
        code, _, _ = self.run_cli("me", "todo", "--goal", "そこそこ")
        self.assertEqual(code, 2)


class MeCardCommandTests(CliTestCase):
    def test_registering_a_card_then_seeing_it_as_owned(self):
        code, out, _ = self.run_cli("me", "card", "88", "--level", "60", "--master-rank", "5", "--trained")
        self.assertEqual(code, 0)
        self.assertIn("登録しました", out)
        _, listing, _ = self.run_cli("me", "cards", "ミク")
        self.assertIn("○ #88", listing)

    def test_the_owned_count_is_shown(self):
        self.run_cli("me", "card", "88")
        _, out, _ = self.run_cli("me", "cards", "ミク")
        self.assertIn("1 / 8 枚", out)

    def test_removing_a_card(self):
        self.run_cli("me", "card", "88")
        code, out, _ = self.run_cli("me", "card", "88", "--remove")
        self.assertEqual(code, 0)
        self.assertIn("外しました", out)
        code, _, _ = self.run_cli("me", "card", "88", "--remove")
        self.assertEqual(code, 2)

    def test_a_card_outside_the_master_data_is_refused(self):
        code, _, err = self.run_cli("me", "card", "999999")
        self.assertEqual(code, 2)
        self.assertIn("マスターデータ", err)

    def test_cards_can_be_filtered_by_rarity(self):
        _, out, _ = self.run_cli("--json", "me", "cards", "ミク", "--rarity", "4")
        payload = json.loads(out)
        self.assertEqual([c["id"] for c in payload["missing"]], [88])
        self.assertEqual(payload["owned"], [])


class MeEventCommandTests(CliTestCase):
    def test_pace_for_a_named_event(self):
        code, out, _ = self.run_cli(
            "me", "event", "--event-id", "1", "--points", "250000", "--target", "1000000"
        )
        self.assertEqual(code, 0)
        self.assertIn("750,000", out)

    def test_reaching_the_target_is_reported(self):
        code, out, _ = self.run_cli(
            "me", "event", "--event-id", "1", "--points", "1000000", "--target", "1000000"
        )
        self.assertEqual(code, 0)
        self.assertIn("達成済み", out)

    def test_an_unknown_event_exits_with_code_two(self):
        code, _, _ = self.run_cli("me", "event", "--event-id", "99999", "--points", "0", "--target", "1")
        self.assertEqual(code, 2)

    def test_without_a_running_event_it_says_so(self):
        code, _, err = self.run_cli("me", "event", "--points", "0", "--target", "1")
        self.assertEqual(code, 2)
        self.assertIn("開催中のイベント", err)


class MeMarkCommandTests(CliTestCase):
    def test_marking_every_master_chart_then_progress_reads_full(self):
        code, out, _ = self.run_cli("me", "mark", "--difficulty", "master", "--clear", "clear")
        self.assertEqual(code, 0)
        self.assertIn("3 件を記録しました", out)
        _, progress, _ = self.run_cli("--json", "me", "progress", "--difficulty", "master")
        self.assertTrue(all(row["cleared"] == row["total"] for row in json.loads(progress)))

    def test_a_dry_run_reports_without_saving(self):
        code, out, _ = self.run_cli("me", "mark", "--difficulty", "master", "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("保存していません", out)
        _, export, _ = self.run_cli("me", "export")
        self.assertEqual(json.loads(export)["plays"], [])

    def test_the_second_run_reports_nothing_left_to_do(self):
        self.run_cli("me", "mark", "--difficulty", "master")
        _, out, _ = self.run_cli("me", "mark", "--difficulty", "master")
        self.assertIn("すでに同等以上: 3 件", out)

    def test_a_level_range_limits_what_is_marked(self):
        _, out, _ = self.run_cli(
            "--json", "me", "mark", "--difficulty", "master", "--max-level", "29"
        )
        payload = json.loads(out)
        self.assertEqual(payload["total"], 2)
        self.assertEqual(sorted(row["play_level"] for row in payload["charts"]), [26, 29])

    def test_full_combo_can_be_marked_too(self):
        _, out, _ = self.run_cli("me", "mark", "--difficulty", "master", "--clear", "fc")
        self.assertIn("フルコンボ", out)

    def test_an_unknown_difficulty_exits_with_code_two(self):
        code, _, err = self.run_cli("me", "mark", "--difficulty", "lunatic")
        self.assertEqual(code, 2)
        self.assertIn("エラー", err)

    def test_an_unknown_clear_type_exits_with_code_two(self):
        code, _, _ = self.run_cli("me", "mark", "--clear", "だいたい")
        self.assertEqual(code, 2)
