from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone

from proseka.models import Card, Character, Event, Music, MusicDifficulty, from_epoch_ms, to_epoch_ms

from support import FIXTURES


def load(table):
    return json.loads((FIXTURES / f"{table}.json").read_text(encoding="utf-8"))


class TimestampTests(unittest.TestCase):
    def test_round_trip(self):
        moment = datetime(2020, 10, 9, 6, 0, tzinfo=timezone.utc)
        self.assertEqual(from_epoch_ms(to_epoch_ms(moment)), moment)

    def test_naive_datetime_is_treated_as_utc(self):
        self.assertEqual(to_epoch_ms(datetime(1970, 1, 1, 0, 0, 1)), 1000)

    def test_bad_values_become_none(self):
        for value in (None, "", "abc", object()):
            self.assertIsNone(from_epoch_ms(value))


class CharacterTests(unittest.TestCase):
    def setUp(self):
        self.characters = [Character.parse(row) for row in load("gameCharacters")]
        self.by_id = {c.id: c for c in self.characters}

    def test_full_name_order(self):
        ichika = self.by_id[1]
        self.assertEqual(ichika.full_name, "星乃 一歌")
        self.assertEqual(ichika.full_name_ruby, "ほしの いちか")
        self.assertEqual(ichika.full_name_english, "Ichika Hoshino")

    def test_single_name_character_has_no_stray_space(self):
        kaito = self.by_id[26]
        self.assertEqual(kaito.full_name, "KAITO")
        self.assertEqual(kaito.full_name_english, "Kaito")

    def test_virtual_singer_flag(self):
        self.assertTrue(self.by_id[21].is_virtual_singer)
        self.assertFalse(self.by_id[1].is_virtual_singer)

    def test_raw_record_is_preserved(self):
        self.assertEqual(self.by_id[1].get("modelName"), "01ichika")
        self.assertIsNone(self.by_id[1].get("noSuchField"))


class MusicTests(unittest.TestCase):
    def test_credit_deduplicates_names(self):
        music = Music.parse(
            {"id": 1, "title": "Tell Your World", "lyricist": "kz", "composer": "kz", "arranger": "kz"}
        )
        self.assertEqual(music.credit, "kz")

    def test_credit_keeps_distinct_names_in_order(self):
        music = Music.parse({"lyricist": "A", "composer": "B", "arranger": "A"})
        self.assertEqual(music.credit, "A / B")

    def test_published_at_is_parsed(self):
        music = Music.parse(load("musics")[0])
        self.assertIsInstance(music.published_at, datetime)
        self.assertEqual(music.published_at.tzinfo, timezone.utc)


class DifficultyTests(unittest.TestCase):
    def test_label(self):
        chart = MusicDifficulty.parse(
            {"id": 5, "musicId": 1, "musicDifficulty": "master", "playLevel": 26, "totalNoteCount": 811}
        )
        self.assertEqual(chart.label, "MASTER 26")


class CardTests(unittest.TestCase):
    def test_rarity_stars(self):
        self.assertEqual(Card.parse({"cardRarityType": "rarity_4"}).rarity_stars, "★★★★")
        self.assertEqual(Card.parse({"cardRarityType": "rarity_birthday"}).rarity_stars, "🎂")

    def test_unknown_rarity_falls_back_to_the_raw_value(self):
        self.assertEqual(Card.parse({"cardRarityType": "rarity_x"}).rarity_stars, "rarity_x")


class EventTests(unittest.TestCase):
    def setUp(self):
        self.event = Event.parse(load("events")[0])

    def test_running_between_start_and_aggregate(self):
        inside = self.event.start_at
        self.assertTrue(self.event.is_running(inside))
        self.assertTrue(self.event.is_running(self.event.aggregate_at))

    def test_not_running_before_or_after(self):
        before = from_epoch_ms(to_epoch_ms(self.event.start_at) - 1000)
        after = from_epoch_ms(to_epoch_ms(self.event.aggregate_at) + 1000)
        self.assertFalse(self.event.is_running(before))
        self.assertFalse(self.event.is_running(after))

    def test_naive_now_is_accepted(self):
        naive = self.event.start_at.replace(tzinfo=None)
        self.assertTrue(self.event.is_running(naive))

    def test_event_without_dates_is_never_running(self):
        self.assertFalse(Event.parse({"id": 99}).is_running())


if __name__ == "__main__":
    unittest.main()
