from __future__ import annotations

import unittest

from proseka.play import ClearType, OwnedCard, PlayerProfile, PlayRecord, parse_difficulty


class ClearTypeTests(unittest.TestCase):
    def test_order_expresses_at_least_this_good(self):
        self.assertGreater(ClearType.ALL_PERFECT, ClearType.FULL_COMBO)
        self.assertGreater(ClearType.FULL_COMBO, ClearType.CLEAR)
        self.assertGreater(ClearType.CLEAR, ClearType.NOT_CLEARED)

    def test_parse_accepts_english_abbreviations(self):
        self.assertIs(ClearType.parse("fc"), ClearType.FULL_COMBO)
        self.assertIs(ClearType.parse("AP"), ClearType.ALL_PERFECT)
        self.assertIs(ClearType.parse("full-combo"), ClearType.FULL_COMBO)

    def test_parse_accepts_japanese(self):
        self.assertIs(ClearType.parse("フルコン"), ClearType.FULL_COMBO)
        self.assertIs(ClearType.parse("オールパーフェクト"), ClearType.ALL_PERFECT)
        self.assertIs(ClearType.parse("未クリア"), ClearType.NOT_CLEARED)

    def test_parse_accepts_numbers_and_itself(self):
        self.assertIs(ClearType.parse(2), ClearType.FULL_COMBO)
        self.assertIs(ClearType.parse("3"), ClearType.ALL_PERFECT)
        self.assertIs(ClearType.parse(ClearType.CLEAR), ClearType.CLEAR)

    def test_labels_and_codes(self):
        self.assertEqual(ClearType.ALL_PERFECT.code, "all_perfect")
        self.assertEqual(ClearType.FULL_COMBO.label, "フルコンボ")

    def test_unknown_value_names_the_valid_ones(self):
        with self.assertRaises(ValueError) as caught:
            ClearType.parse("だいたいクリア")
        self.assertIn("full_combo", str(caught.exception))


class DifficultyTests(unittest.TestCase):
    def test_aliases(self):
        for value in ("master", "MASTER", " mas ", "マスター", "ma"):
            with self.subTest(value=value):
                self.assertEqual(parse_difficulty(value), "master")

    def test_unknown_difficulty_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_difficulty("lunatic")


class PlayRecordTests(unittest.TestCase):
    def test_key_identifies_one_chart(self):
        record = PlayRecord(music_id=3, difficulty="master")
        self.assertEqual(record.key, "3:master")

    def test_round_trip_through_a_dict(self):
        record = PlayRecord(music_id=3, difficulty="master", clear=ClearType.FULL_COMBO, score=1180000)
        restored = PlayRecord.from_dict(record.to_dict())
        self.assertEqual(restored, record)

    def test_from_dict_normalizes_loose_input(self):
        record = PlayRecord.from_dict({"music_id": "3", "difficulty": "マスター", "clear": "fc", "score": ""})
        self.assertEqual(record.music_id, 3)
        self.assertEqual(record.difficulty, "master")
        self.assertIs(record.clear, ClearType.FULL_COMBO)
        self.assertIsNone(record.score)


class OwnedCardTests(unittest.TestCase):
    def test_round_trip(self):
        card = OwnedCard(card_id=88, level=60, master_rank=5, special_training=True)
        self.assertEqual(OwnedCard.from_dict(card.to_dict()), card)

    def test_defaults_are_conservative(self):
        card = OwnedCard.from_dict({"card_id": 1})
        self.assertIsNone(card.level)
        self.assertEqual(card.master_rank, 0)
        self.assertFalse(card.special_training)


class PlayerProfileTests(unittest.TestCase):
    def test_round_trip_keeps_the_id_as_text(self):
        profile = PlayerProfile(name="くろねこ", user_id="123456789012345", rank=120)
        restored = PlayerProfile.from_dict(profile.to_dict())
        self.assertEqual(restored, profile)
        self.assertIsInstance(restored.user_id, str)

    def test_empty_profile_has_no_rank(self):
        self.assertIsNone(PlayerProfile.from_dict({}).rank)


if __name__ == "__main__":
    unittest.main()
