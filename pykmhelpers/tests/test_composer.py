"""Unit tests for composer sharding: sample limits, naming and layout state.

The full compose flow is covered by ``test_pipeline_e2e.py``.
"""

import shutil
import tempfile
import unittest
from pathlib import Path

import yaml

from pykmhelpers.operations.builder import _backup_pattern, backup_name
from pykmhelpers.pipeline.composer import IndexComposer, load_layout, max_samples_for
from pykmhelpers.pipeline.index_db import IndexDefinitionTools


class TestMaxSamplesFor(unittest.TestCase):
    def test_unlimited(self):
        self.assertEqual(max_samples_for(1000, 0), 0)
        self.assertEqual(max_samples_for(0, 1000), 0)

    def test_rounded_down_to_a_multiple_of_8(self):
        # 8 * 10000 / 1000 = 80 samples
        self.assertEqual(max_samples_for(1000, 10000), 80)
        # 8 * 9999 / 1000 = 79 samples -> 72
        self.assertEqual(max_samples_for(1000, 9999), 72)

    def test_never_below_8(self):
        """A row is byte aligned, so a shard always holds at least 8 samples."""
        self.assertEqual(max_samples_for(10**9, 1000), 8)


class TestShardNaming(unittest.TestCase):
    def setUp(self):
        self.tools = IndexDefinitionTools()

    def test_without_sharding(self):
        self.assertEqual(self.tools.get_merge_name("idx", 0), "idx_g0")
        self.assertEqual(self.tools.get_shard_name("idx_g0"), "idx_g0")
        self.assertEqual(
            self.tools.get_part_name("idx_g0", "initial"), "idx_g0_initial"
        )

    def test_with_sharding(self):
        self.assertEqual(self.tools.get_merge_name("idx", 0, 2), "idx_g0_p2")
        self.assertEqual(self.tools.get_shard_name("idx_g0", 2), "idx_g0_p2")
        self.assertEqual(
            self.tools.get_part_name("idx_g0_p2", "initial"), "idx_g0_p2_initial"
        )

    def test_part_carries_the_group_of_its_shard(self):
        """A part is named after its shard, so 'g' never means the span."""
        shard = self.tools.get_shard_name(self.tools.get_merge_name("idx", 0), 2)
        self.assertEqual(
            self.tools.get_part_name(shard, "initial"), "idx_g0_p2_initial"
        )

    def test_a_part_is_not_mistaken_for_an_update_backup(self):
        """The default session id is a timestamp, like the backup suffix."""
        part = self.tools.get_part_name("idx_g0", "20260927_120000")
        self.assertFalse(_backup_pattern("idx_g0").match(part))
        self.assertTrue(
            _backup_pattern("idx_g0").match(backup_name("idx_g0", "20260927_120000"))
        )


class TestCurrentShard(unittest.TestCase):
    def composer(self):
        return IndexComposer(name="idx")

    def props(self, max_samples, shards=None):
        return {
            "id": 0,
            "name": "idx_g0",
            "max_samples": max_samples,
            "shards": shards or [],
        }

    def test_first_shard_without_sharding_has_no_suffix(self):
        props = self.props(0)
        shard = self.composer()._current_shard(props, 0)
        self.assertEqual(shard["name"], "idx_g0")
        self.assertIsNone(shard["id"])

    def test_new_shard_when_full(self):
        props = self.props(8)
        composer = self.composer()
        shard = composer._current_shard(props, 1000)
        self.assertEqual(shard["name"], "idx_g0_p0")

        shard["samples"] = 8
        shard = composer._current_shard(props, 1000)
        self.assertEqual(shard["name"], "idx_g0_p1")
        self.assertEqual(shard["samples"], 0)
        self.assertEqual(len(props["shards"]), 2)

    def test_last_shard_is_filled_first(self):
        props = self.props(8, [{"id": 0, "name": "idx_g0_p0", "samples": 3}])
        shard = self.composer()._current_shard(props, 1000)
        self.assertEqual(shard["name"], "idx_g0_p0")
        self.assertEqual(len(props["shards"]), 1)

    def test_shard_follows_the_recorded_span_name(self):
        """A shard derives from the span's name, not from its group ordinal."""
        props = self.props(8)
        props["name"] = "idx_g7"
        shard = self.composer()._current_shard(props, 1000)
        self.assertEqual(shard["name"], "idx_g7_p0")


class TestLayout(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.path = str(self.tmp / "idx_layout.yaml")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_round_trip(self):
        props = {
            76: {
                "id": 0,
                "name": "idx_g0",
                "max_samples": 80,
                "total_samples": 85,
                "updates": 2,
                "partition_count": 16,
                "shards": [
                    {"id": 0, "name": "idx_g0_p0", "samples": 80},
                    {"id": 1, "name": "idx_g0_p1", "samples": 5},
                ],
            }
        }
        IndexComposer(name="idx")._write_layout(self.path, 1.1, 10000, 10, props)
        base, shard_size, minim_size, loaded = load_layout(self.path)

        self.assertEqual((base, shard_size, minim_size), (1.1, 10000, 10))
        self.assertEqual(loaded, props)

    def test_layout_without_sharding(self):
        """A pre-sharding layout reads as one unlimited shard keeping its name."""
        legacy = {"type": "layout", "data": {"base": 1.1, "map": {76: "idx_g0"}}}
        with open(self.path, "w") as f:
            yaml.dump(legacy, f)

        base, shard_size, minim_size, loaded = load_layout(self.path)
        self.assertEqual((base, shard_size, minim_size), (1.1, 0, 0))
        self.assertEqual(loaded[76]["name"], "idx_g0")
        self.assertEqual(loaded[76]["max_samples"], 0)
        self.assertEqual(loaded[76]["partition_count"], 0)
        self.assertEqual(loaded[76]["total_samples"], 0)
        self.assertEqual(loaded[76]["updates"], 0)
        self.assertEqual(loaded[76]["shards"], [])


if __name__ == "__main__":
    unittest.main()
