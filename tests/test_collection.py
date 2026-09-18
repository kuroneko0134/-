from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from proseka import ProsekaClient
from proseka.collection import Collection
from proseka.play import ClearType, OwnedCard, PlayRecord
from proseka.store import PlayerStore

from support import FakeTransport


class CollectionTestCase(unittest.TestCase):
    """Fixtures hold three songs: Tell Your World (MASTER 26), ロキ (29), テオ (32)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.client = ProsekaClient("jp", cache_dir=root / "cache", transport=FakeTransport())
        self.store = PlayerStore.open("jp", data_dir=root / "data")
        self.collection = Collection(self.client, self.store)

    def tearDown(self):
        self.tmp.cleanup()

    def record(self, music_id, difficulty, clear, score=None):
        self.store.set_record(PlayRecord(music_id, difficulty, ClearType.parse(clear), score))


class ChartProgressTests(CollectionTestCase):
    def test_every_chart_of_a_difficulty_is_listed_lowest_level_first(self):
        rows = self.collection.chart_progress(difficulty="master")
        self.assertEqual([row.chart.play_level for row in rows], [26, 29, 32])
        self.assertEqual([row.music.title for row in rows][0], "Tell Your World")

    def test_charts_without_a_record_read_as_not_cleared(self):
        row = self.collection.chart_progress(difficulty="master")[0]
        self.assertIsNone(row.record)
        self.assertIs(row.clear, ClearType.NOT_CLEARED)
        self.assertIsNone(row.score)

    def test_a_record_is_attached_to_its_chart(self):
        self.record(3, "master", "fc", 1180000)
        row = [r for r in self.collection.chart_progress(difficulty="master") if r.music.id == 3][0]
        self.assertIs(row.clear, ClearType.FULL_COMBO)
        self.assertEqual(row.score, 1180000)
        self.assertTrue(row.reached(ClearType.CLEAR))
        self.assertFalse(row.reached(ClearType.ALL_PERFECT))

    def test_filtering_by_level(self):
        rows = self.collection.chart_progress(level=32)
        self.assertEqual([(r.music.title, r.chart.difficulty) for r in rows], [("テオ", "master")])

    def test_filtering_by_song(self):
        rows = self.collection.chart_progress(music_id=1)
        self.assertEqual(len(rows), 6)
        self.assertTrue(all(row.music.id == 1 for row in rows))

    def test_a_japanese_difficulty_name_is_accepted(self):
        self.assertEqual(
            len(self.collection.chart_progress(difficulty="マスター")),
            len(self.collection.chart_progress(difficulty="master")),
        )


class TodoTests(CollectionTestCase):
    def test_reached_charts_drop_off_the_list(self):
        self.record(3, "master", "fc")
        titles = [row.music.title for row in self.collection.todo("fc", difficulty="master")]
        self.assertNotIn("テオ", titles)
        self.assertIn("ロキ", titles)

    def test_the_closest_charts_come_first(self):
        self.record(2, "master", "clear")
        rows = self.collection.todo("ap", difficulty="master")
        self.assertEqual(rows[0].music.title, "ロキ")
        self.assertIs(rows[0].clear, ClearType.CLEAR)

    def test_a_full_combo_still_counts_as_todo_for_an_all_perfect_goal(self):
        self.record(3, "master", "fc")
        titles = [row.music.title for row in self.collection.todo("ap", difficulty="master")]
        self.assertIn("テオ", titles)

    def test_an_empty_list_once_everything_is_done(self):
        for music_id in (1, 2, 3):
            self.record(music_id, "master", "ap")
        self.assertEqual(self.collection.todo("ap", difficulty="master"), [])

    def test_level_filter_narrows_the_list(self):
        rows = self.collection.todo("clear", difficulty="master", level=29)
        self.assertEqual([row.music.title for row in rows], ["ロキ"])


class SummaryTests(CollectionTestCase):
    def test_level_summary_counts_each_goal_separately(self):
        self.record(1, "master", "ap")
        self.record(2, "master", "clear")
        summaries = {s.level: s for s in self.collection.level_summary("master")}
        self.assertEqual(
            (summaries[26].total, summaries[26].cleared, summaries[26].full_combo, summaries[26].all_perfect),
            (1, 1, 1, 1),
        )
        self.assertEqual((summaries[29].cleared, summaries[29].full_combo), (1, 0))
        self.assertEqual(summaries[32].cleared, 0)

    def test_rate_and_remaining(self):
        self.record(2, "master", "clear")
        summary = {s.level: s for s in self.collection.level_summary("master")}[29]
        self.assertEqual(summary.rate(ClearType.CLEAR), 1.0)
        self.assertEqual(summary.rate(ClearType.ALL_PERFECT), 0.0)
        self.assertEqual(summary.remaining, 0)

    def test_clear_counts_cover_every_chart(self):
        self.record(1, "master", "fc")
        counts = self.collection.clear_counts(difficulty="master")
        self.assertEqual(counts["full_combo"], 1)
        self.assertEqual(counts["not_cleared"], 2)
        self.assertEqual(sum(counts.values()), 3)


class CardCollectionTests(CollectionTestCase):
    def test_owned_and_missing_are_split(self):
        self.store.set_card(OwnedCard(88))
        owned, missing = self.collection.card_collection(21)
        self.assertEqual([card.id for card in owned], [88])
        self.assertEqual(len(missing), 7)

    def test_rarity_filter_applies_to_both_halves(self):
        self.store.set_card(OwnedCard(4))
        owned, missing = self.collection.card_collection(1, rarity="4")
        self.assertEqual([card.id for card in owned], [4])
        self.assertEqual(missing, [])

    def test_owned_cards_resolve_to_master_records(self):
        self.store.set_card(OwnedCard(4))
        self.store.set_card(OwnedCard(88))
        self.assertEqual([card.id for card in self.collection.owned_cards()], [4, 88])

    def test_cards_that_left_the_master_data_are_reported(self):
        self.store.set_card(OwnedCard(999999))
        self.assertEqual(self.collection.unknown_card_ids(), [999999])
        self.assertEqual([c.id for c in self.collection.owned_cards()], [])


class EventPaceTests(CollectionTestCase):
    def setUp(self):
        super().setUp()
        self.event = self.client.event(1)

    def test_pace_is_the_remaining_points_over_the_remaining_hours(self):
        now = self.event.aggregate_at - timedelta(hours=10)
        pace = self.collection.event_pace(250000, 1000000, event=self.event, now=now)
        self.assertEqual(pace.remaining, 750000)
        self.assertAlmostEqual(pace.hours_left, 10.0, places=3)
        self.assertAlmostEqual(pace.points_per_hour, 75000.0, places=1)
        self.assertFalse(pace.reached)

    def test_reaching_the_target_needs_no_more_points(self):
        now = self.event.start_at + timedelta(hours=1)
        pace = self.collection.event_pace(1000000, 1000000, event=self.event, now=now)
        self.assertTrue(pace.reached)
        self.assertEqual(pace.remaining, 0)
        self.assertEqual(pace.points_per_hour, 0.0)

    def test_after_the_cut_off_the_pace_is_unreachable(self):
        now = self.event.aggregate_at + timedelta(hours=1)
        pace = self.collection.event_pace(10, 1000000, event=self.event, now=now)
        self.assertEqual(pace.hours_left, 0.0)
        self.assertIsNone(pace.points_per_hour)

    def test_a_naive_now_is_treated_as_utc(self):
        now = (self.event.aggregate_at - timedelta(hours=10)).replace(tzinfo=None)
        pace = self.collection.event_pace(0, 100, event=self.event, now=now)
        self.assertEqual(pace.now.tzinfo, timezone.utc)

    def test_no_running_event_means_no_pace(self):
        moment = datetime(2019, 1, 1, tzinfo=timezone.utc)
        self.assertIsNone(self.collection.event_pace(0, 100, now=moment))


class ResolveMusicTests(CollectionTestCase):
    def test_an_id_resolves_to_itself(self):
        self.assertEqual(self.collection.resolve_music_id("3"), 3)

    def test_an_exact_title_wins_over_a_partial_match(self):
        self.assertEqual(self.collection.resolve_music_id("Tell Your World"), 1)

    def test_a_single_partial_match_is_accepted(self):
        self.assertEqual(self.collection.resolve_music_id("テ"), 3)

    def test_an_ambiguous_query_is_rejected_with_the_candidates(self):
        with self.assertRaises(ValueError) as caught:
            self.collection.resolve_music_id("o")
        self.assertIn("テオ", str(caught.exception))

    def test_an_unknown_song_is_rejected(self):
        with self.assertRaises(ValueError):
            self.collection.resolve_music_id("存在しない曲")


if __name__ == "__main__":
    unittest.main()


class MarkAllTests(CollectionTestCase):
    """Bulk marking writes down play already done; it never plays anything."""

    def test_marking_every_master_chart_as_cleared(self):
        result = self.collection.mark_all("clear", difficulty="master")
        self.assertEqual((result.total, result.changed_count), (3, 3))
        self.assertEqual(self.collection.clear_counts(difficulty="master")["clear"], 3)

    def test_running_it_twice_changes_nothing_the_second_time(self):
        self.collection.mark_all("clear", difficulty="master")
        again = self.collection.mark_all("clear", difficulty="master")
        self.assertEqual((again.changed_count, again.unchanged_count), (0, 3))

    def test_a_better_existing_record_is_kept(self):
        self.record(3, "master", "ap")
        self.collection.mark_all("clear", difficulty="master")
        self.assertIs(self.store.record(3, "master").clear, ClearType.ALL_PERFECT)

    def test_overwrite_lowers_a_better_record_when_asked(self):
        self.record(3, "master", "ap")
        result = self.collection.mark_all("clear", difficulty="master", overwrite=True)
        self.assertEqual(result.changed_count, 3)
        self.assertIs(self.store.record(3, "master").clear, ClearType.CLEAR)

    def test_marking_a_higher_goal_upgrades_existing_records(self):
        self.collection.mark_all("clear", difficulty="master")
        result = self.collection.mark_all("fc", difficulty="master")
        self.assertEqual(result.changed_count, 3)
        self.assertIs(self.store.record(2, "master").clear, ClearType.FULL_COMBO)

    def test_a_dry_run_writes_nothing(self):
        result = self.collection.mark_all("clear", difficulty="master", dry_run=True)
        self.assertEqual(result.changed_count, 3)
        self.assertTrue(result.dry_run)
        self.assertEqual(len(self.store), 0)

    def test_level_filters_narrow_the_target(self):
        self.assertEqual(self.collection.mark_all("clear", difficulty="master", level=29).total, 1)
        self.assertEqual(
            self.collection.mark_all("clear", difficulty="master", max_level=29, dry_run=True).total, 2
        )
        self.assertEqual(
            self.collection.mark_all("clear", difficulty="master", min_level=29, dry_run=True).total, 2
        )

    def test_a_level_range_can_be_bounded_on_both_sides(self):
        result = self.collection.mark_all(
            "clear", difficulty="master", min_level=27, max_level=30, dry_run=True
        )
        self.assertEqual([row.chart.play_level for row in result.changed], [29])

    def test_marking_other_difficulties_leaves_master_alone(self):
        self.collection.mark_all("clear", difficulty="append")
        self.assertEqual(self.collection.clear_counts(difficulty="master")["not_cleared"], 3)

    def test_an_unknown_clear_type_is_rejected(self):
        with self.assertRaises(ValueError):
            self.collection.mark_all("だいたいクリア", difficulty="master")

    def test_an_unknown_difficulty_is_rejected(self):
        with self.assertRaises(ValueError):
            self.collection.mark_all("clear", difficulty="lunatic")
