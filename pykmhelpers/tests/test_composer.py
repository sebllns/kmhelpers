"""Unit tests for composer sharding: sample limits, naming and layout state.

The full compose flow is covered by ``test_pipeline_e2e.py``.
"""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

import yaml

from pykmhelpers.core.bloom_filter import SpanManager
from pykmhelpers.pipeline.composer import (
    IndexComposer,
    budget_samples_for,
    layout_path,
    load_layout,
    load_layout_bitw,
    load_layout_sessions,
    load_layout_shard_budget,
    max_samples_for,
)
from pykmhelpers.pipeline.index_db import (
    IndexDB,
    IndexDefinition,
    IndexDefinitionTools,
    Sample,
)


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

    def test_abundance_bits_per_sample(self):
        """An abundance index stores bitw bits per sample: bitw times fewer fit."""
        self.assertEqual(max_samples_for(1000, 10000, 2), 40)
        self.assertEqual(max_samples_for(1000, 10000, 0), 80)


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


class TestBudgetModel(unittest.TestCase):
    """Logan model: budget / base**span samples, rounded up to a multiple of 8."""

    def test_unlimited(self):
        self.assertEqual(budget_samples_for(168, 1.1, 0), 0)

    def test_logan_genomic_chunks(self):
        for span, expected in [(168, 15288), (184, 3328), (218, 136), (250, 8)]:
            self.assertEqual(budget_samples_for(span, 1.1, 2**37), expected)

    def test_logan_v1_base_2(self):
        self.assertEqual(budget_samples_for(30, 2.0, 2**37), 128)

    def test_never_below_8(self):
        self.assertEqual(budget_samples_for(300, 1.1, 2**37), 8)

    def test_shard_budget(self):
        composer = IndexComposer(name="idx", shard_budget=2**43)
        max_samples = composer._max_samples(168, SpanManager(b=1.1), 1.1, 0)
        self.assertEqual(max_samples, budget_samples_for(168, 1.1, 2**43))

    def test_shard_size_replaces_the_budget(self):
        """A byte size is used instead of the budget, even when larger."""
        manager = SpanManager(b=1.1)
        size = 10**15
        composer = IndexComposer(name="idx", shard_size=size)
        self.assertEqual(
            composer._max_samples(168, manager, 1.1, size),
            max_samples_for(manager.get_bf_size(168), size),
        )

    def test_zero_budget_is_unlimited(self):
        composer = IndexComposer(name="idx", shard_budget=0)
        self.assertEqual(composer._max_samples(168, SpanManager(b=1.1), 1.1, 0), 0)

    def test_budget_and_size_are_exclusive(self):
        with self.assertRaises(ValueError):
            IndexComposer(name="idx", shard_budget=2**43, shard_size=1000)


class TestComposeSharding(unittest.TestCase):
    """Default shard budget on a new index, kept or re-sharded on updates."""

    SPAN = 144  # 10**6 k-mers in base 1.1

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.samples = str(self.tmp / "samples.jsonl")
        with open(self.samples, "w") as f:
            f.write('{"k": 25}\n')
            for n in range(3):
                f.write(
                    f'{{"name": "S{n}", "files": ["S{n}.fa"], "kmer_count": 1000000}}\n'
                )
        self.profile = str(self.tmp / "profile.yaml")
        with open(self.profile, "w") as f:
            yaml.dump(
                {
                    "span_base": 1.1,
                    "false_positive_rate": 0.25,
                    "default_profile": "p",
                    "profiles": {"p": {"span_list": [self.SPAN]}},
                },
                f,
            )
        self.out = str(self.tmp / "compose")
        self.layout = layout_path(self.out, "idx")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def compose(self, session, profile=True, **kwargs):
        # Database names are unique per process: free those of earlier runs
        IndexDB._instances.clear()
        IndexComposer(
            profiles_file=self.profile if profile else None,
            layout_file=None if profile else self.layout,
            name="idx",
            **kwargs,
        ).run(input_file=self.samples, output_dir=self.out, run_id=session)
        with open(self.layout) as f:
            return yaml.safe_load(f)["data"]

    def test_new_index_uses_the_default_budget(self):
        data = self.compose("initial")
        entry = data["map"][self.SPAN]
        self.assertEqual((data["shard_budget"], data["shard_size"]), (2**43, 0))
        self.assertEqual(
            entry["max_samples"], budget_samples_for(self.SPAN, 1.1, 2**43)
        )
        self.assertNotIn("chunk_samples", entry)
        self.assertEqual(entry["shards"][0]["name"], "idx_g0_p0")

    def test_zero_budget_keeps_a_single_unlimited_index(self):
        data = self.compose("initial", shard_budget=0)
        entry = data["map"][self.SPAN]
        self.assertEqual(entry["max_samples"], 0)
        self.assertEqual(entry["shards"][0]["name"], "idx_g0")

    def test_update_keeps_the_layout_rule(self):
        self.compose("initial", shard_budget=0)
        data = self.compose("upd", profile=False)
        self.assertEqual(data["shard_budget"], 0)
        self.assertEqual(data["map"][self.SPAN]["max_samples"], 0)

    def test_explicit_budget_reshards_an_update(self):
        self.compose("initial", shard_budget=0)
        data = self.compose("upd", profile=False, shard_budget=2**40)
        self.assertEqual(data["shard_budget"], 2**40)
        self.assertEqual(
            data["map"][self.SPAN]["max_samples"],
            budget_samples_for(self.SPAN, 1.1, 2**40),
        )

    def test_size_switches_the_rule_of_an_update(self):
        self.compose("initial")
        data = self.compose("upd", profile=False, shard_size=10**9)
        self.assertEqual((data["shard_budget"], data["shard_size"]), (0, 10**9))
        bf_size = SpanManager(b=1.1).get_bf_size(self.SPAN)
        self.assertEqual(
            data["map"][self.SPAN]["max_samples"], max_samples_for(bf_size, 10**9)
        )

    def test_update_keeps_a_size_rule(self):
        self.compose("initial", shard_size=10**9)
        data = self.compose("upd", profile=False)
        self.assertEqual((data["shard_budget"], data["shard_size"]), (0, 10**9))


class TestSessionSampleList(TestComposeSharding):
    """The session copies its sample list, or points to it (copy_list=False)."""

    def shard_sample_file(self, session="initial"):
        session_dir = Path(self.out) / "idx" / session
        shard = yaml.safe_load((session_dir / "shards" / "idx_g0_p0.yaml").read_text())
        sample_file = shard["data"]["idx_g0_p0_" + session]["sample_file"]
        return session_dir, sample_file

    def test_copy_by_default(self):
        self.compose("initial")
        session_dir, sample_file = self.shard_sample_file()
        self.assertEqual(sample_file, "../samples.jsonl")
        self.assertTrue((session_dir / "samples.jsonl").is_file())

    def test_list_in_the_design_dir_is_relative(self):
        self.compose("initial", copy_list=False)
        session_dir, sample_file = self.shard_sample_file()
        # shards/ -> initial/ -> idx/ -> compose/ -> the design dir
        self.assertEqual(sample_file, "../../../../samples.jsonl")
        self.assertFalse((session_dir / "samples.jsonl").exists())

    def test_list_outside_is_absolute(self):
        elsewhere = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, elsewhere, ignore_errors=True)
        self.samples = shutil.copy(self.samples, elsewhere / "list.jsonl")
        self.compose("initial", copy_list=False)
        _, sample_file = self.shard_sample_file()
        self.assertEqual(sample_file, os.path.realpath(self.samples))

    def test_rerun_without_copy_removes_the_old_copy(self):
        self.compose("initial")
        self.compose("initial", copy_list=False)
        session_dir, _ = self.shard_sample_file()
        self.assertFalse((session_dir / "samples.jsonl").exists())


class TestKmerRatio(TestComposeSharding):
    """Each shard records its k-mer ratio: occurrences per counted k-mer."""

    def write_samples(self, header, totals):
        with open(self.samples, "w") as f:
            f.write(header + "\n")
            for n, total in enumerate(totals):
                entry = {"name": f"S{n}", "files": [f"S{n}.fa"], "kmer_count": 1000000}
                if total:
                    entry["kmer_total"] = total
                f.write(json.dumps(entry) + "\n")

    def ratios(self, **kwargs):
        self.compose("initial", **kwargs)
        session_dir = Path(self.out) / "idx" / "initial"
        index = yaml.safe_load((session_dir / "index.yaml").read_text())
        (shard,) = IndexDefinitionTools().load_db(
            str(session_dir / "shards" / "idx_g0_p0.yaml")
        )
        part = shard.index_table["idx_g0_p0_initial"]
        return index["shards"]["idx_g0_p0"]["kmer_ratio"], part.kmer_ratio

    def test_largest_ratio_of_the_samples(self):
        self.write_samples('{"k": 25, "assembled": false}', [2000000, 7500000, 0])
        # S2 has no kmer_total: the raw-read default (4) counts too
        self.assertEqual(self.ratios(), (7.5, 7.5))

    def test_raw_read_default(self):
        self.write_samples('{"k": 25, "assembled": false}', [0, 0, 0])
        self.assertEqual(self.ratios(), (4.0, 4.0))

    def test_assembled_default(self):
        self.write_samples('{"k": 25}', [0, 0, 0])
        self.assertEqual(self.ratios(), (1.0, 1.0))

    def test_option_multiplies_the_ratio(self):
        self.write_samples('{"k": 25, "assembled": false}', [3000000, 0, 0])
        self.assertEqual(self.ratios(kmer_ratio=2), (8.0, 8.0))

    def test_ratio_is_at_least_one(self):
        self.write_samples('{"k": 25}', [900000, 900000, 900000])
        self.assertEqual(self.ratios(), (1.0, 1.0))

    def test_non_positive_option_is_refused(self):
        with self.assertRaises(ValueError):
            IndexComposer(name="idx", kmer_ratio=0)


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
        shard = self.composer()._current_shard(props)
        self.assertEqual(shard["name"], "idx_g0")
        self.assertIsNone(shard["id"])

    def test_new_shard_when_full(self):
        props = self.props(8)
        composer = self.composer()
        shard = composer._current_shard(props)
        self.assertEqual(shard["name"], "idx_g0_p0")

        shard["samples"] = 8
        shard = composer._current_shard(props)
        self.assertEqual(shard["name"], "idx_g0_p1")
        self.assertEqual(shard["samples"], 0)
        self.assertEqual(len(props["shards"]), 2)

    def test_last_shard_is_filled_first(self):
        props = self.props(8, [{"id": 0, "name": "idx_g0_p0", "samples": 3}])
        shard = self.composer()._current_shard(props)
        self.assertEqual(shard["name"], "idx_g0_p0")
        self.assertEqual(len(props["shards"]), 1)

    def test_shard_follows_the_recorded_span_name(self):
        """A shard derives from the span's name, not from its group ordinal."""
        props = self.props(8)
        props["name"] = "idx_g7"
        shard = self.composer()._current_shard(props)
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

    def test_bitw_round_trip(self):
        IndexComposer(name="idx", bitw=2)._write_layout(self.path, 1.1, 0, 10, {})
        self.assertEqual(load_layout_bitw(self.path), 2)

    def test_sessions_round_trip(self):
        IndexComposer(name="idx")._write_layout(
            self.path, 1.1, 0, 10, {}, ["initial", "upd"]
        )
        self.assertEqual(load_layout_sessions(self.path), ["initial", "upd"])

    def test_shard_budget_round_trip(self):
        composer = IndexComposer(name="idx", shard_budget=2**40)
        composer._write_layout(self.path, 1.1, 0, 10, {})
        self.assertEqual(load_layout_shard_budget(self.path), 2**40)

    def write_legacy(self, **fields):
        legacy = {
            "type": "layout",
            "data": {"base": 1.1, "map": {76: "idx_g0"}, **fields},
        }
        with open(self.path, "w") as f:
            yaml.dump(legacy, f)

    def test_layout_without_budget_has_no_limit(self):
        self.write_legacy()
        self.assertEqual(load_layout_shard_budget(self.path), 0)

    def test_chunk_model_layout_reads_as_a_shard_budget(self):
        self.write_legacy(chunk_budget=2**37, shard_chunks=64)
        self.assertEqual(load_layout_shard_budget(self.path), 2**43)

    def test_layout_with_a_size_has_no_budget(self):
        self.write_legacy(chunk_budget=2**37, shard_chunks=64, shard_size=10**9)
        self.assertEqual(load_layout_shard_budget(self.path), 0)

    def test_layout_without_bitw_is_presence_absence(self):
        legacy = {"type": "layout", "data": {"base": 1.1, "map": {76: "idx_g0"}}}
        with open(self.path, "w") as f:
            yaml.dump(legacy, f)
        self.assertEqual(load_layout_bitw(self.path), 0)

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


class TestAbundanceDefinition(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.tools = IndexDefinitionTools()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def round_trip(self, bitw):
        # Item names are unique per process, so each test uses its own
        name = f"idx_bitw{bitw}"
        i = IndexDefinition(name=f"{name}_g0_initial", bf_size=1024, bitw=bitw)
        path = str(self.tmp / f"{name}.yaml")
        self.tools.save_db(IndexDB(name=name, index_table={i.name: i}), path)
        # Loading creates a database of the same name
        IndexDB._instances.pop(name, None)
        return self.tools.load_db(path)[0].index_table[i.name], path

    def test_bitw_round_trip(self):
        i, _ = self.round_trip(2)
        self.assertEqual(i.bitw, 2)

    def test_presence_absence_writes_no_bitw(self):
        """Presence/absence definitions are unchanged, and read back as bitw=0."""
        i, path = self.round_trip(0)
        self.assertEqual(i.bitw, 0)
        self.assertNotIn("bitw:", Path(path).read_text())

    def test_storage_counts_bitw_bits_per_sample(self):
        pa = IndexDefinition(name="pa", bf_size=8 * 4096)
        ab = IndexDefinition(name="ab", bf_size=8 * 4096, bitw=2)
        for i in (pa, ab):
            for n in range(16):
                i.add_sample(f"{i.name}_s{n}", Sample())
        self.assertEqual(
            ab.get_bf_specs().matrix_size, 2 * pa.get_bf_specs().matrix_size
        )


if __name__ == "__main__":
    unittest.main()
