from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from proseka.errors import ProsekaError
from proseka.play import ClearType, OwnedCard, PlayerProfile, PlayRecord
from proseka.store import PlayerStore, default_data_dir, parse_play_csv, write_play_csv


TITLES = {"tell your world": 1, "ロキ": 2, "テオ": 3}


def resolve(text: str) -> int:
    key = text.strip().lower()
    if key.isdigit():
        return int(key)
    if key in TITLES:
        return TITLES[key]
    raise ValueError(f"no song matches {text!r}")


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = PlayerStore.open("jp", data_dir=Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_missing_file_starts_an_empty_store(self):
        self.assertEqual(len(self.store), 0)
        self.assertEqual(self.store.profile, PlayerProfile(updated_at=self.store.profile.updated_at))

    def test_records_survive_a_save_and_reload(self):
        self.store.profile = PlayerProfile(name="くろねこ", user_id="1234", rank=120)
        self.store.set_record(PlayRecord(3, "master", ClearType.FULL_COMBO, 1180000))
        self.store.set_card(OwnedCard(88, level=60, master_rank=5, special_training=True))
        self.store.save()

        reloaded = PlayerStore.open("jp", data_dir=Path(self.tmp.name))
        self.assertEqual(reloaded.profile.name, "くろねこ")
        self.assertEqual(reloaded.record(3, "master").score, 1180000)
        self.assertTrue(reloaded.owns(88))
        self.assertEqual(reloaded.cards[88].master_rank, 5)

    def test_saved_file_is_readable_json(self):
        self.store.set_record(PlayRecord(2, "append", ClearType.ALL_PERFECT))
        path = self.store.save()
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["version"], 1)
        self.assertEqual(payload["plays"][0]["clear"], "all_perfect")

    def test_a_worse_result_does_not_overwrite_a_better_one(self):
        self.store.set_record(PlayRecord(3, "master", ClearType.FULL_COMBO, 1180000))
        self.store.set_record(PlayRecord(3, "master", ClearType.CLEAR, 900000))
        kept = self.store.record(3, "master")
        self.assertIs(kept.clear, ClearType.FULL_COMBO)
        self.assertEqual(kept.score, 1180000)

    def test_a_better_result_replaces_the_old_one(self):
        self.store.set_record(PlayRecord(3, "master", ClearType.CLEAR, 900000))
        self.store.set_record(PlayRecord(3, "master", ClearType.ALL_PERFECT, 1200000))
        kept = self.store.record(3, "master")
        self.assertIs(kept.clear, ClearType.ALL_PERFECT)
        self.assertEqual(kept.score, 1200000)

    def test_overwrite_can_be_forced(self):
        self.store.set_record(PlayRecord(3, "master", ClearType.ALL_PERFECT, 1200000))
        self.store.set_record(PlayRecord(3, "master", ClearType.CLEAR, 100), keep_best=False)
        self.assertIs(self.store.record(3, "master").clear, ClearType.CLEAR)

    def test_records_of_the_same_song_at_different_difficulties_coexist(self):
        self.store.set_record(PlayRecord(2, "master", ClearType.CLEAR))
        self.store.set_record(PlayRecord(2, "append", ClearType.ALL_PERFECT))
        self.assertEqual(len(self.store), 2)

    def test_difficulty_aliases_reach_the_same_record(self):
        self.store.set_record(PlayRecord(2, "master", ClearType.CLEAR))
        self.assertIsNotNone(self.store.record(2, "マスター"))

    def test_removal(self):
        self.store.set_record(PlayRecord(2, "master", ClearType.CLEAR))
        self.assertTrue(self.store.remove_record(2, "master"))
        self.assertFalse(self.store.remove_record(2, "master"))
        self.store.set_card(OwnedCard(4))
        self.assertTrue(self.store.remove_card(4))
        self.assertFalse(self.store.remove_card(4))

    def test_records_are_sorted_by_song_then_difficulty(self):
        self.store.set_record(PlayRecord(3, "master", ClearType.CLEAR))
        self.store.set_record(PlayRecord(2, "append", ClearType.CLEAR))
        self.store.set_record(PlayRecord(2, "easy", ClearType.CLEAR))
        self.assertEqual(
            [(r.music_id, r.difficulty) for r in self.store],
            [(2, "easy"), (2, "append"), (3, "master")],
        )

    def test_a_newer_schema_is_refused_rather_than_misread(self):
        self.store.save()
        payload = json.loads(self.store.path.read_text(encoding="utf-8"))
        payload["version"] = 99
        self.store.path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(ProsekaError) as caught:
            PlayerStore.open("jp", data_dir=Path(self.tmp.name))
        self.assertIn("newer version", str(caught.exception))

    def test_a_corrupt_file_is_reported_with_its_path(self):
        self.store.save()
        self.store.path.write_text("{ broken", encoding="utf-8")
        with self.assertRaises(ProsekaError) as caught:
            PlayerStore.open("jp", data_dir=Path(self.tmp.name))
        self.assertIn("player.json", str(caught.exception))

    def test_each_region_keeps_its_own_file(self):
        self.store.set_record(PlayRecord(1, "master", ClearType.CLEAR))
        self.store.save()
        other = PlayerStore.open("en", data_dir=Path(self.tmp.name))
        self.assertEqual(len(other), 0)


class CsvTests(unittest.TestCase):
    def test_titles_and_ids_both_resolve(self):
        text = "music,difficulty,clear\nテオ,master,fc\n2,append,ap\n"
        records = parse_play_csv(text, resolve)
        self.assertEqual([(r.music_id, r.difficulty) for r in records], [(3, "master"), (2, "append")])
        self.assertIs(records[0].clear, ClearType.FULL_COMBO)

    def test_japanese_headers_are_understood(self):
        text = "曲名,難易度,クリア,スコア\nロキ,マスター,クリア,980000\n"
        record = parse_play_csv(text, resolve)[0]
        self.assertEqual((record.music_id, record.difficulty, record.score), (2, "master", 980000))

    def test_scores_may_carry_thousands_separators(self):
        text = "music,difficulty,score\nテオ,master,\"1,180,000\"\n"
        self.assertEqual(parse_play_csv(text, resolve)[0].score, 1180000)

    def test_a_missing_clear_column_means_cleared(self):
        record = parse_play_csv("music,difficulty\nテオ,master\n", resolve)[0]
        self.assertIs(record.clear, ClearType.CLEAR)

    def test_blank_rows_are_skipped(self):
        records = parse_play_csv("music,difficulty\n\nテオ,master\n", resolve)
        self.assertEqual(len(records), 1)

    def test_a_bad_row_names_its_line_number(self):
        text = "music,difficulty\nテオ,master\nロキ,ちょうむずかしい\n"
        with self.assertRaises(ProsekaError) as caught:
            parse_play_csv(text, resolve)
        self.assertIn("line 3", str(caught.exception))

    def test_an_unknown_song_names_its_line_number(self):
        with self.assertRaises(ProsekaError) as caught:
            parse_play_csv("music,difficulty\n知らない曲,master\n", resolve)
        self.assertIn("line 2", str(caught.exception))

    def test_a_missing_song_column_is_rejected(self):
        with self.assertRaises(ProsekaError) as caught:
            parse_play_csv("difficulty,clear\nmaster,fc\n", resolve)
        self.assertIn("song column", str(caught.exception))

    def test_an_empty_csv_is_rejected(self):
        with self.assertRaises(ProsekaError):
            parse_play_csv("", resolve)

    def test_export_round_trips_back_through_the_parser(self):
        original = [
            PlayRecord(3, "master", ClearType.FULL_COMBO, 1180000),
            PlayRecord(2, "append", ClearType.ALL_PERFECT),
        ]
        text = write_play_csv(original, {3: "テオ", 2: "ロキ"})
        self.assertIn("テオ", text)
        restored = parse_play_csv(text, resolve)
        self.assertEqual(
            [(r.music_id, r.difficulty, r.clear, r.score) for r in restored],
            [(r.music_id, r.difficulty, r.clear, r.score) for r in original],
        )


class DataDirTests(unittest.TestCase):
    def setUp(self):
        self.saved = {k: os.environ.get(k) for k in ("PROSEKA_DATA_DIR", "XDG_DATA_HOME")}

    def tearDown(self):
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_explicit_override_wins(self):
        os.environ["PROSEKA_DATA_DIR"] = "/tmp/proseka-data"
        self.assertEqual(default_data_dir(), Path("/tmp/proseka-data"))

    def test_xdg_data_home_is_honoured(self):
        os.environ.pop("PROSEKA_DATA_DIR", None)
        os.environ["XDG_DATA_HOME"] = "/tmp/xdg"
        self.assertEqual(default_data_dir(), Path("/tmp/xdg/proseka"))


if __name__ == "__main__":
    unittest.main()
