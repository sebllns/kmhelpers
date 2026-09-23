"""Unit tests for the index_ops components that do not need kmindex.

Covers status aggregation, build parameter sizing, input source filtering,
sample resolution and script export. The full build/merge flow is covered by
``test_pipeline_e2e.py``.
"""

import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from pykmhelpers.pipeline.index_ops import ApplyStatus, IndexOpsConfig
from pykmhelpers.pipeline.index_ops.report import merge_status, run_status
from pykmhelpers.pipeline.index_ops.samples import SampleResolver
from pykmhelpers.pipeline.index_ops.script import ScriptRecorder
from pykmhelpers.pipeline.index_ops.sizing import BuildParams, resolve_build_params
from pykmhelpers.pipeline.index_ops.sources import (
    IndexDefinitionSource,
    SpanRegistrySource,
)

S, F, P, N = "SUCCESS", "FAILED", "PARTIAL", "NONE"


def make_config(**kwargs):
    return IndexOpsConfig(
        workdir="w", index_data_folder="d", registry_dir="r", **kwargs
    )


def make_definition(name="idx", span=1, partition_count=0, samples=None):
    return SimpleNamespace(
        name=name,
        span=span,
        bf_size=27160,
        fp_rate=0.25,
        partition_count=partition_count,
        samples=samples or {},
        sample_file=None,
    )


class FakeCache:
    """DbCache stand-in: each path yields one db holding the given definitions."""

    def __init__(self, definitions=None):
        self.definitions = definitions or []
        self.loaded = []

    def load(self, path, idt):
        self.loaded.append(Path(path).stem)
        return [SimpleNamespace(index_table={i.name: i for i in self.definitions})]

    def source_dir(self, db):
        return None


class TestStatus(unittest.TestCase):
    def test_run_status(self):
        self.assertIs(run_status([]), ApplyStatus.NONE)
        self.assertIs(run_status([N, N]), ApplyStatus.NONE)
        self.assertIs(run_status([S, N]), ApplyStatus.SUCCESS)
        self.assertIs(run_status([F, N]), ApplyStatus.FAILED)
        self.assertIs(run_status([F, S]), ApplyStatus.PARTIAL)
        self.assertIs(run_status([P, S]), ApplyStatus.PARTIAL)

    def test_merge_status(self):
        self.assertIs(merge_status([]), ApplyStatus.SUCCESS)
        self.assertIs(merge_status([F, F]), ApplyStatus.FAILED)
        self.assertIs(merge_status([F, N]), ApplyStatus.PARTIAL)
        self.assertIs(merge_status([N, N]), ApplyStatus.NONE)
        self.assertIs(merge_status([S, N]), ApplyStatus.SUCCESS)


class TestResolveBuildParams(unittest.TestCase):
    def test_explicit_threads_keep_storage_partitions(self):
        i = make_definition(partition_count=2)
        params = resolve_build_params(i, 10, make_config(kmindex_threads=3))
        self.assertEqual(params, BuildParams(threads=3, partitions=4))
        self.assertEqual(i.partition_count, 2)

    def test_partition_override(self):
        config = make_config(kmindex_threads=3, partition_count=8)
        params = resolve_build_params(make_definition(partition_count=2), 10, config)
        self.assertEqual(params.partitions, 8)

    def test_auto_sizing_fits(self):
        config = make_config(limits='{"ram": 8000000000, "files": 4096, "threads": 4}')
        params = resolve_build_params(make_definition(), 7, config)
        self.assertIsNone(params.chunk_size)
        self.assertGreaterEqual(params.partitions, 4)
        self.assertGreater(params.threads, 0)

    def test_auto_sizing_chunks_under_low_files_limit(self):
        config = make_config(limits='{"ram": 8000000000, "files": 4, "threads": 4}')
        params = resolve_build_params(make_definition(), 7, config)
        self.assertIsNotNone(params.chunk_size)
        self.assertLess(params.chunk_size, 7)


class TestIndexDefinitionSource(unittest.TestCase):
    def setUp(self):
        self.cache = FakeCache(
            [
                make_definition("a", span=1),
                make_definition("b", span=2),
                make_definition("", span=1),
            ]
        )

    def names(self, **filters):
        source = IndexDefinitionSource(make_config(**filters), self.cache)
        return [i.name for i in source.load("x.yaml", None, {}).definitions]

    def test_unnamed_definitions_are_dropped(self):
        self.assertEqual(self.names(), ["a", "b"])

    def test_filters(self):
        self.assertEqual(self.names(filter_names=["b"]), ["b"])
        self.assertEqual(self.names(filter_spans=[1]), ["a"])
        self.assertEqual(self.names(filter_names=["a"], filter_spans=[2]), [])


class TestSpanRegistrySource(unittest.TestCase):
    DATA = {
        "data": {
            1: {"indices": {"t1": ["p1", "p2"]}},
            2: {"indices": {"t2": ["p3"]}},
        }
    }

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        for part in ("p1", "p2", "p3"):
            (self.tmp / f"{part}.yaml").touch()
        self.registry = str(self.tmp / "reg.yaml")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def load(self, data=None, **filters):
        cache = FakeCache()
        plan = SpanRegistrySource(make_config(**filters), cache).load(
            self.registry, None, data or self.DATA
        )
        return plan.merges, cache.loaded

    def test_all(self):
        merges, loaded = self.load()
        self.assertEqual(merges, {"t1": ["p1", "p2"], "t2": ["p3"]})
        self.assertEqual(loaded, ["p1", "p2", "p3"])

    def test_filter_span(self):
        self.assertEqual(self.load(filter_spans=[2]), ({"t2": ["p3"]}, ["p3"]))

    def test_filter_target_name(self):
        self.assertEqual(
            self.load(filter_names=["t1"]), ({"t1": ["p1", "p2"]}, ["p1", "p2"])
        )

    def test_filter_part_name_builds_without_merge(self):
        self.assertEqual(self.load(filter_names=["p2"]), ({}, ["p2"]))

    def test_scripts_group_parts_under_their_target(self):
        cache = FakeCache()
        plan = SpanRegistrySource(make_config(), cache).load(
            self.registry, None, self.DATA
        )
        self.assertEqual(plan.scripts, {"p1": "t1", "p2": "t1", "p3": "t2"})
        self.assertEqual(plan.script_of("p2"), "t1")
        self.assertEqual(plan.script_of("unknown"), "unknown")

    def test_missing_indices(self):
        with self.assertRaises(ValueError):
            self.load({"data": {1: {"infos": {}}}})

    def test_missing_part_file(self):
        with self.assertRaises(FileNotFoundError):
            self.load({"data": {1: {"indices": {"t": ["nope"]}}}})


class TestSampleResolver(unittest.TestCase):
    def build(self, samples, rootpath=None, check_files=False):
        i = make_definition(
            samples={s.name or str(n): s for n, s in enumerate(samples)}
        )
        resolver = SampleResolver(rootpath, check_files, FakeCache())
        return resolver.build_fof(i)

    def test_rootpath_applies_to_relative_paths_only(self):
        s = SimpleNamespace(name="s", files=["a.fa", "/abs/b.fa"])
        fof, issues = self.build([s], rootpath="/root")
        self.assertEqual(issues, [])
        self.assertEqual(fof.get_sample_count(), 1)
        self.assertIn("/root/a.fa", str(fof.samples["s"]))
        self.assertIn("/abs/b.fa", str(fof.samples["s"]))
        self.assertNotIn("/root/abs", str(fof.samples["s"]))

    def test_invalid_samples_become_issues(self):
        samples = [
            SimpleNamespace(name="ok", files=["a.fa"]),
            SimpleNamespace(name="empty", files=[]),
            SimpleNamespace(name="", files=["b.fa"]),
            SimpleNamespace(name="_", files=["c.fa"]),
        ]
        fof, issues = self.build(samples)
        self.assertEqual(fof.get_sample_count(), 1)
        self.assertEqual(len(issues), 2)

    def test_missing_files_are_checked_on_request(self):
        s = SimpleNamespace(name="s", files=["/does/not/exist.fa"])
        self.assertEqual(self.build([s])[1], [])
        self.assertEqual(len(self.build([s], check_files=True)[1]), 1)


class TestScriptRecorder(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.assets = self.tmp / "assets"
        self.assets.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def lines(self, name):
        return (self.assets / name).read_text().splitlines()

    def test_one_script_per_group_and_runner(self):
        rec = ScriptRecorder(str(self.tmp))
        rec.select("b")
        rec.add(f"build {self.tmp}/b_p0", "build b_p0")
        rec.select("a")
        rec.add("build a_p0", "build a_p0")
        rec.select("b")
        rec.add("merge b", "merge b_p0 -> b")
        rec.write(str(self.assets))

        header = [
            "#!/usr/bin/bash",
            "set -euo pipefail",
            f"WORKDIR='{self.tmp}'",
            "cd ${WORKDIR}",
        ]
        ts = "$(date '+%F %T')"
        self.assertEqual(
            self.lines("b.sh"),
            header
            + [
                f'echo "{ts} [b] build b_p0"',
                "build ${WORKDIR}/b_p0",
                f'echo "{ts} [b] merge b_p0 -> b"',
                "merge b",
                f'echo "{ts} [b] done"',
            ],
        )
        self.assertEqual(
            self.lines("a.sh"),
            header
            + [f'echo "{ts} [a] build a_p0"', "build a_p0", f'echo "{ts} [a] done"'],
        )
        self.assertEqual(
            self.lines("kmhelpers_apply.sh"),
            header
            + [
                f'echo "{ts} Running assets/b.sh"',
                'bash "${WORKDIR}/assets/b.sh"',
                f'echo "{ts} Running assets/a.sh"',
                'bash "${WORKDIR}/assets/a.sh"',
            ],
        )

    def test_add_requires_selection(self):
        with self.assertRaises(RuntimeError):
            ScriptRecorder(str(self.tmp)).add("cmd", "step")

    def test_write_creates_directory_and_entry_runner(self):
        rec = ScriptRecorder(str(self.tmp))
        rec.select("a")
        rec.add("build a_p0", "step")
        session_dir = self.assets / "initial"
        rec.write(str(session_dir))
        rec.write_entry(str(self.assets), str(session_dir / "kmhelpers_apply.sh"))

        self.assertTrue((session_dir / "a.sh").is_file())
        self.assertEqual(
            self.lines("initial/kmhelpers_apply.sh")[-1],
            'bash "${WORKDIR}/assets/initial/a.sh"',
        )
        self.assertEqual(
            self.lines("kmhelpers_apply.sh")[-1],
            'bash "${WORKDIR}/assets/initial/kmhelpers_apply.sh"',
        )

    def test_rewrite_backs_up(self):
        for cmd in ("first", "second"):
            rec = ScriptRecorder(str(self.tmp))
            rec.select("a")
            rec.add(cmd, "step")
            rec.write(str(self.assets))
        self.assertIn("second", self.lines("a.sh"))
        self.assertIn("first", self.lines("a.sh.bak"))


if __name__ == "__main__":
    unittest.main()
