from __future__ import annotations

import unittest

from proseka.regions import REGIONS, get_region


class RegionTests(unittest.TestCase):
    def test_default_region_points_at_the_japanese_mirror(self):
        region = get_region("jp")
        self.assertEqual(
            region.table_url("musics"),
            "https://raw.githubusercontent.com/Sekai-World/sekai-master-db-diff/main/musics.json",
        )

    def test_lookup_ignores_case_and_padding(self):
        self.assertIs(get_region("  EN "), REGIONS["en"])

    def test_every_region_has_a_distinct_repository(self):
        repositories = [region.repository for region in REGIONS.values()]
        self.assertEqual(len(repositories), len(set(repositories)))

    def test_unknown_region_names_the_valid_ones(self):
        with self.assertRaises(ValueError) as caught:
            get_region("mars")
        self.assertIn("jp", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
