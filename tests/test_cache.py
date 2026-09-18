from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from proseka.cache import TableCache, default_cache_dir


class TableCacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = TableCache(Path(self.tmp.name), "jp")

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_table_reads_as_none(self):
        self.assertIsNone(self.cache.read("musics"))

    def test_round_trip_keeps_payload_and_etag(self):
        self.cache.write("musics", [{"id": 1, "title": "テル・ユア・ワールド"}], '"abc"')
        entry = self.cache.read("musics")
        self.assertEqual(entry.payload[0]["title"], "テル・ユア・ワールド")
        self.assertEqual(entry.etag, '"abc"')
        self.assertTrue(entry.is_fresh(60))

    def test_entry_expires_after_ttl(self):
        entry = self.cache.write("events", [], None)
        self.assertFalse(entry.is_fresh(ttl=1, now=time.time() + 5))
        self.assertGreaterEqual(entry.age(now=time.time() + 5), 5)

    def test_corrupt_payload_reads_as_none(self):
        self.cache.write("cards", [{"id": 1}], None)
        (self.cache.dir / "cards.json").write_text("{not json", encoding="utf-8")
        self.assertIsNone(self.cache.read("cards"))

    def test_corrupt_metadata_still_yields_the_payload(self):
        self.cache.write("cards", [{"id": 1}], '"e"')
        (self.cache.dir / "cards.meta.json").write_text("nonsense", encoding="utf-8")
        entry = self.cache.read("cards")
        self.assertEqual(entry.payload, [{"id": 1}])
        self.assertIsNone(entry.etag)

    def test_clear_removes_every_file_and_counts_them(self):
        self.cache.write("cards", [], None)
        self.cache.write("events", [], None)
        self.assertEqual(self.cache.clear(), 4)
        self.assertEqual(self.cache.clear(), 0)

    def test_write_leaves_no_temporary_files_behind(self):
        self.cache.write("musics", [{"id": 1}], None)
        names = sorted(p.name for p in self.cache.dir.iterdir())
        self.assertEqual(names, ["musics.json", "musics.meta.json"])

    def test_touch_refreshes_the_timestamp(self):
        first = self.cache.write("musics", [{"id": 1}], '"v1"')
        time.sleep(0.01)
        second = self.cache.touch("musics", first)
        self.assertGreater(second.fetched_at, first.fetched_at)
        self.assertEqual(second.payload, first.payload)
        self.assertEqual(second.etag, '"v1"')


class CacheDirTests(unittest.TestCase):
    def setUp(self):
        self.saved = {k: os.environ.get(k) for k in ("PROSEKA_CACHE_DIR", "XDG_CACHE_HOME")}

    def tearDown(self):
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_explicit_override_wins(self):
        os.environ["PROSEKA_CACHE_DIR"] = "/tmp/proseka-test"
        self.assertEqual(default_cache_dir(), Path("/tmp/proseka-test"))

    def test_xdg_cache_home_is_honoured(self):
        os.environ.pop("PROSEKA_CACHE_DIR", None)
        os.environ["XDG_CACHE_HOME"] = "/tmp/xdg"
        self.assertEqual(default_cache_dir(), Path("/tmp/xdg/proseka"))


if __name__ == "__main__":
    unittest.main()
