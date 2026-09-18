from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from proseka import ProsekaClient
from proseka.errors import OfflineError, TransportError

from support import FakeTransport, seed_cache


class ClientTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.transport = FakeTransport()
        self.client = ProsekaClient(
            "jp", cache_dir=Path(self.tmp.name), transport=self.transport
        )

    def tearDown(self):
        self.tmp.cleanup()


class FetchAndCacheTests(ClientTestCase):
    def test_first_call_downloads_and_second_call_uses_the_cache(self):
        self.client.table("musics")
        self.client.table("musics")
        self.assertEqual(self.transport.call_count, 1)

    def test_a_fresh_process_reuses_the_cache_on_disk(self):
        self.client.table("musics")
        other = ProsekaClient("jp", cache_dir=Path(self.tmp.name), transport=self.transport)
        self.assertTrue(other.table("musics"))
        self.assertEqual(self.transport.call_count, 1)

    def test_expired_cache_is_revalidated_with_the_stored_etag(self):
        self.client.table("musics")
        stale = ProsekaClient(
            "jp", cache_dir=Path(self.tmp.name), ttl=0, transport=self.transport
        )
        rows = stale.table("musics")
        self.assertEqual(self.transport.conditional[-1], '"v1"')
        self.assertTrue(rows)
        self.assertEqual(self.transport.call_count, 2)

    def test_refresh_ignores_a_fresh_cache(self):
        self.client.table("musics")
        self.client.table("musics", refresh=True)
        self.assertEqual(self.transport.call_count, 2)

    def test_changed_etag_replaces_the_cached_payload(self):
        self.client.table("musics")
        self.transport.etag = '"v2"'
        self.transport.set_payload("musics", [{"id": 999, "title": "新曲"}])
        rows = self.client.table("musics", refresh=True)
        self.assertEqual(rows, [{"id": 999, "title": "新曲"}])
        self.assertEqual(self.client.musics()[0].title, "新曲")

    def test_network_failure_falls_back_to_the_cached_copy(self):
        self.client.table("musics")
        self.transport.fail = True
        offline_client = ProsekaClient(
            "jp", cache_dir=Path(self.tmp.name), ttl=0, transport=self.transport
        )
        self.assertTrue(offline_client.table("musics"))

    def test_network_failure_without_a_cache_is_an_error(self):
        self.transport.fail = True
        with self.assertRaises(TransportError):
            self.client.table("musics")

    def test_offline_mode_refuses_to_download(self):
        client = ProsekaClient(
            "jp", cache_dir=Path(self.tmp.name), offline=True, transport=self.transport
        )
        with self.assertRaises(OfflineError):
            client.table("musics")
        self.assertEqual(self.transport.call_count, 0)

    def test_offline_mode_reads_a_pre_seeded_cache(self):
        seed_cache(Path(self.tmp.name))
        client = ProsekaClient(
            "jp", cache_dir=Path(self.tmp.name), offline=True, transport=self.transport
        )
        self.assertTrue(client.characters())
        self.assertEqual(self.transport.call_count, 0)

    def test_sync_reports_record_counts(self):
        counts = self.client.sync(["gameCharacters", "unitProfiles"])
        self.assertEqual(counts, {"gameCharacters": 4, "unitProfiles": 2})

    def test_clear_cache_removes_the_files(self):
        self.client.table("musics")
        self.assertEqual(self.client.clear_cache(), 2)
        self.assertIsNone(self.client.cache.read("musics"))

    def test_invalid_json_is_reported_clearly(self):
        self.transport.payloads["musics"] = b"<html>404</html>"
        with self.assertRaises(Exception) as caught:
            self.client.table("musics")
        self.assertIn("valid JSON", str(caught.exception))


class CharacterLookupTests(ClientTestCase):
    def test_lookup_by_id(self):
        self.assertEqual(self.client.character(1).full_name, "星乃 一歌")
        self.assertIsNone(self.client.character(9999))

    def test_search_by_kanji_kana_and_english(self):
        for query in ("一歌", "ほしの", "ichika", "HOSHINO"):
            with self.subTest(query=query):
                self.assertEqual([c.id for c in self.client.find_characters(query)], [1])

    def test_search_normalizes_width_and_spacing(self):
        self.assertEqual([c.id for c in self.client.find_characters("ﾐｸ")], [21])
        self.assertEqual([c.id for c in self.client.find_characters("星乃 一歌")], [1])

    def test_empty_query_matches_nothing(self):
        self.assertEqual(self.client.find_characters("   "), [])

    def test_unit_lookup_accepts_code_and_display_name(self):
        self.assertEqual(self.client.unit("light_sound").name, "Leo/need")
        self.assertEqual(self.client.unit("Leo/need").unit, "light_sound")
        self.assertIsNone(self.client.unit("存在しないユニット"))

    def test_unit_members(self):
        members = self.client.characters_in_unit("Leo/need")
        self.assertEqual([m.id for m in members], [1, 2])
        self.assertTrue(all(m.is_virtual_singer for m in self.client.characters_in_unit("piapro")))


class MusicLookupTests(ClientTestCase):
    def test_search_by_title_and_creator(self):
        self.assertEqual([m.id for m in self.client.find_musics("Tell Your World")], [1])
        self.assertTrue(self.client.find_musics("kz"))

    def test_difficulties_are_ordered_from_easy_to_append(self):
        charts = self.client.difficulties_for(1)
        self.assertEqual(
            [c.difficulty for c in charts][:5],
            ["easy", "normal", "hard", "expert", "master"],
        )

    def test_charts_at_level_can_be_filtered_by_difficulty(self):
        pairs = self.client.charts_at_level(26, "master")
        self.assertTrue(pairs)
        self.assertTrue(all(chart.difficulty == "master" for _, chart in pairs))
        self.assertTrue(all(chart.play_level == 26 for _, chart in pairs))

    def test_charts_at_an_unused_level_is_empty(self):
        self.assertEqual(self.client.charts_at_level(99), [])


class CardLookupTests(ClientTestCase):
    def test_cards_belong_to_the_requested_character(self):
        cards = self.client.cards_for_character(1)
        self.assertTrue(cards)
        self.assertTrue(all(card.character_id == 1 for card in cards))

    def test_rarity_filter_accepts_several_spellings(self):
        expected = [c.id for c in self.client.cards_for_character(1, rarity="rarity_4")]
        for spelling in ("4", "4*", "★4", "rarity_4"):
            with self.subTest(spelling=spelling):
                got = [c.id for c in self.client.cards_for_character(1, rarity=spelling)]
                self.assertEqual(got, expected)

    def test_attribute_filter(self):
        cards = self.client.cards_for_character(1, attr="COOL")
        self.assertTrue(all(card.attr == "cool" for card in cards))

    def test_a_character_object_can_be_passed_instead_of_an_id(self):
        ichika = self.client.character(1)
        self.assertEqual(
            [c.id for c in self.client.cards_for_character(ichika)],
            [c.id for c in self.client.cards_for_character(1)],
        )


class EventLookupTests(ClientTestCase):
    def test_current_event_during_the_first_event(self):
        first = self.client.event(1)
        current = self.client.current_event(first.start_at + timedelta(hours=1))
        self.assertEqual(current.id, 1)

    def test_no_current_event_long_before_the_first_one(self):
        self.assertIsNone(self.client.current_event(datetime(2019, 1, 1, tzinfo=timezone.utc)))

    def test_next_event_is_the_earliest_one_still_ahead(self):
        moment = datetime(2019, 1, 1, tzinfo=timezone.utc)
        self.assertEqual(self.client.next_event(moment).id, 1)

    def test_no_next_event_after_they_have_all_started(self):
        self.assertIsNone(self.client.next_event(datetime(2030, 1, 1, tzinfo=timezone.utc)))

    def test_recent_events_are_newest_first_and_limited(self):
        events = self.client.recent_events(2, now=datetime(2030, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(len(events), 2)
        self.assertGreater(events[0].start_at, events[1].start_at)

    def test_recent_events_with_a_zero_limit(self):
        self.assertEqual(self.client.recent_events(0), [])


class RegionTests(unittest.TestCase):
    def test_each_region_caches_into_its_own_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            transport = FakeTransport()
            jp = ProsekaClient("jp", cache_dir=Path(tmp), transport=transport)
            en = ProsekaClient("en", cache_dir=Path(tmp), transport=transport)
            jp.table("musics")
            en.table("musics")
            self.assertEqual(transport.call_count, 2)
            self.assertIn("sekai-master-db-en-diff", transport.requests[1])
            self.assertTrue((Path(tmp) / "jp" / "musics.json").is_file())
            self.assertTrue((Path(tmp) / "en" / "musics.json").is_file())

    def test_unknown_region_is_rejected_at_construction(self):
        with self.assertRaises(ValueError):
            ProsekaClient("mars")


if __name__ == "__main__":
    unittest.main()
