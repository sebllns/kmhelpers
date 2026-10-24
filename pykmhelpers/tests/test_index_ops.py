"""Unit tests for the index_ops components that do not need kmindex.

Covers status aggregation, build parameter sizing, input source filtering,
sample resolution and script export. The full build/publish flow is covered by
``test_pipeline_e2e.py``.
"""

import multiprocessing
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import yaml

from pykmhelpers.pipeline.fof import FofManager
from pykmhelpers.pipeline.index_ops import ApplyStatus, IndexOpsConfig
from pykmhelpers.pipeline.index_ops.executor import IndexExecutor
from pykmhelpers.pipeline.index_ops.layout import LayoutStore, record_shard_partitions
from pykmhelpers.pipeline.index_ops.ops import IndexOps
from pykmhelpers.pipeline.index_ops.paths import BuildPaths, check_index_name
from pykmhelpers.pipeline.index_ops.plan_file import (
    PUBLISH,
    check_fresh,
    job_names,
    load_plan,
    new_plan,
    write_plan,
)
from pykmhelpers.pipeline.index_ops.report import publish_status, run_status
from pykmhelpers.pipeline.index_ops.runner import PlanRunner
from pykmhelpers.pipeline.index_ops.samples import SampleResolver
from pykmhelpers.pipeline.index_ops.script import ScriptRecorder
from pykmhelpers.pipeline.index_ops.sizing import BuildParams, resolve_build_params
from pykmhelpers.pipeline.index_ops.sources import (
    IndexDefinitionSource,
    IndexSessionSource,
    WorkPlan,
    resolve_input,
    session_dir_of,
)

S, F, P, N = "SUCCESS", "FAILED", "PARTIAL", "NONE"


def make_config(**kwargs):
    return IndexOpsConfig(workdir="w", **kwargs)


def make_definition(
    name="idx",
    span=1,
    partition_count=0,
    samples=None,
    minim_size=10,
    bf_size=27160,
    kmer_ratio=1.0,
):
    return SimpleNamespace(
        name=name,
        span=span,
        minim_size=minim_size,
        kmer_ratio=kmer_ratio,
        bf_size=bf_size,
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

    def test_publish_status(self):
        self.assertIs(publish_status([]), ApplyStatus.SUCCESS)
        self.assertIs(publish_status([F, F]), ApplyStatus.FAILED)
        self.assertIs(publish_status([F, N]), ApplyStatus.PARTIAL)
        self.assertIs(publish_status([N, N]), ApplyStatus.NONE)
        self.assertIs(publish_status([S, N]), ApplyStatus.SUCCESS)


class TestResolveBuildParams(unittest.TestCase):
    """The minimizer size comes from the design; the partition count from the
    design (-p) or the limits. Resolving never writes the layout."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.path = str(self.tmp / "idx_layout.yaml")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def layout(self, **span_fields):
        """A layout whose span 1 carries the given fields."""
        data = {
            "type": "layout",
            "data": {"base": 1.1, "map": {1: {"name": "idx_g0", **span_fields}}},
        }
        with open(self.path, "w") as f:
            yaml.dump(data, f)
        return LayoutStore(self.path)

    def test_explicit_threads_keep_stored_partitions(self):
        i = make_definition(partition_count=8)
        params = resolve_build_params(
            i, 10, make_config(kmindex_threads=3), self.layout()
        )
        self.assertEqual(params, BuildParams(3, 8, None, 10))
        self.assertEqual(params.partitions_source, "design")
        self.assertEqual(i.partition_count, 8)

    def test_design_partitions_from_the_layout(self):
        params = resolve_build_params(
            make_definition(), 10, make_config(kmindex_threads=3), self.layout(partition_count=16)
        )
        self.assertEqual(params.partitions, 16)
        self.assertEqual(params.partitions_source, "design")

    def test_minim_size_from_the_definition_then_the_layout(self):
        config = make_config(kmindex_threads=3)
        layout = self.layout()
        params = resolve_build_params(make_definition(minim_size=12), 10, config, layout)
        self.assertEqual(params.minim_size, 12)

        with open(self.path) as f:
            data = yaml.safe_load(f)
        data["data"]["minim_size"] = 9
        with open(self.path, "w") as f:
            yaml.dump(data, f)
        params = resolve_build_params(
            make_definition(minim_size=0), 10, config, LayoutStore(self.path)
        )
        self.assertEqual(params.minim_size, 9)

    def test_no_minim_size_asks_to_redo_the_design(self):
        with self.assertRaisesRegex(ValueError, "redo the design"):
            resolve_build_params(
                make_definition(minim_size=0), 10, make_config(kmindex_threads=3), self.layout()
            )

    def test_the_layout_is_never_written(self):
        layout = self.layout()
        before = Path(self.path).read_bytes()
        config = make_config(limits='{"ram": 8000000000, "files": 4096, "threads": 4}')

        params = resolve_build_params(make_definition(), 7, config, layout)
        self.assertGreaterEqual(params.partitions, 4)
        self.assertEqual(params.partitions_source, "auto")
        self.assertEqual(Path(self.path).read_bytes(), before)
        self.assertIsNone(layout.partition_count(1))

    def test_partitions_sized_on_the_shard_capacity(self):
        """A full shard, not the current session, sets the partition count."""
        config = make_config(limits='{"ram": 200000000, "files": 4096, "threads": 4}')
        small = resolve_build_params(make_definition(), 5, config, self.layout())
        large = resolve_build_params(
            make_definition(), 5, config, self.layout(max_samples=100000)
        )
        self.assertGreaterEqual(large.partitions, small.partitions)

    def test_auto_sizing_fits(self):
        config = make_config(limits='{"ram": 8000000000, "files": 4096, "threads": 4}')
        params = resolve_build_params(make_definition(), 7, config, self.layout())
        self.assertIsNone(params.chunk_size)
        self.assertGreaterEqual(params.partitions, 4)
        self.assertGreater(params.threads, 0)

    def test_kmer_ratio_scales_the_sizing(self):
        """Partitions, then threads at a fixed count, follow k-mer occurrences."""
        config = make_config(limits='{"ram": 8000000000, "files": 4096, "threads": 16}')
        big = 2**33  # bits: about 1.5 G k-mers at fp 0.25
        solid = resolve_build_params(make_definition(bf_size=big), 7, config, self.layout())
        raw = resolve_build_params(
            make_definition(bf_size=big, kmer_ratio=10), 7, config, self.layout()
        )
        self.assertGreater(raw.partitions, solid.partitions)

        fixed = self.layout(partition_count=solid.partitions)
        raw_fixed = resolve_build_params(
            make_definition(bf_size=big, kmer_ratio=10), 7, config, fixed
        )
        self.assertEqual(raw_fixed.partitions, solid.partitions)
        self.assertLess(raw_fixed.threads, solid.threads)

    def test_auto_sizing_chunks_under_low_files_limit(self):
        config = make_config(limits='{"ram": 8000000000, "files": 8, "threads": 4}')
        params = resolve_build_params(make_definition(), 7, config, self.layout())
        self.assertIsNotNone(params.chunk_size)
        self.assertLess(params.chunk_size, 7)

    def test_max_chunks_caps_the_chunk_count(self):
        """A chunk cap raises the chunk size above the open-files optimum."""
        limits = '{"ram": 8000000000, "files": 4096, "threads": 64}'
        capped = resolve_build_params(
            make_definition(),
            1000,
            make_config(limits=limits, max_chunks=4),
            self.layout(),
        )
        self.assertEqual(capped.chunk_size, 250)

    def test_max_chunks_zero_disables_the_cap(self):
        limits = '{"ram": 8000000000, "files": 4096, "threads": 64}'
        params = resolve_build_params(
            make_definition(),
            1000,
            make_config(limits=limits, max_chunks=0),
            self.layout(),
        )
        self.assertEqual(params.chunk_size, 63)

    def test_chunk_model_caps_the_chunk_size(self):
        limits = '{"ram": 8000000000, "files": 4096, "threads": 64}'
        params = resolve_build_params(
            make_definition(),
            1000,
            # ceil8(220 / 1.1**1) = 200 samples per chunk
            make_config(limits=limits, max_chunks=4, chunk_budget=220),
            self.layout(),
        )
        self.assertEqual(params.chunk_size, 200)

    def test_chunk_model_applies_with_explicit_threads(self):
        params = resolve_build_params(
            make_definition(partition_count=8),
            1000,
            make_config(kmindex_threads=3, chunk_budget=220),
            self.layout(),
        )
        self.assertEqual(params, BuildParams(3, 8, 200, 10))

    def test_limits_too_low_for_the_partition_count(self):
        """kmtricks needs at least one open file per partition, plus one."""
        config = make_config(limits='{"ram": 8000000000, "files": 4, "threads": 4}')
        with self.assertRaises(ValueError):
            resolve_build_params(make_definition(), 7, config, self.layout())


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
        self.assertEqual(self.names(filter_names=["*"]), ["a", "b"])

    def test_unmatched_pattern_warns(self):
        with self.assertLogs("pykmhelpers.core.utils", "WARNING") as logs:
            self.assertEqual(self.names(filter_names=["a", "c"]), ["a"])
        self.assertIn("No shard matches c", logs.output[0])

    def test_no_match_is_refused(self):
        with self.assertRaisesRegex(ValueError, "No shard matches c, d"):
            self.names(filter_names=["c", "d"])


class ShardCache:
    """DbCache stand-in: ``shards/<shard>.yaml`` yields that shard's parts."""

    def __init__(self, parts: dict[str, list[str]]):
        self.parts = parts
        self.loaded = []

    def load(self, path, idt):
        shard = Path(path).stem
        self.loaded.append(shard)
        return [
            SimpleNamespace(
                index_table={p: make_definition(p) for p in self.parts[shard]}
            )
        ]


class TestIndexSessionSource(unittest.TestCase):
    PARTS = {"t1": ["p1", "p2"], "t2": ["p3"]}
    DATA = {
        "type": "index_session",
        "shards": {
            "t1": {"span": 1, "file": "shards/t1.yaml"},
            "t2": {"span": 2, "file": "shards/t2.yaml"},
        },
    }

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "shards").mkdir()
        for shard in self.PARTS:
            (self.tmp / "shards" / f"{shard}.yaml").touch()
        self.session = str(self.tmp / "index.yaml")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def load(self, data=None, **filters):
        cache = ShardCache(self.PARTS)
        plan = IndexSessionSource(make_config(**filters), cache).load(
            self.session, None, data or self.DATA
        )
        return plan, cache.loaded

    def test_all(self):
        plan, loaded = self.load()
        self.assertEqual(plan.merges, {"t1": ["p1", "p2"], "t2": ["p3"]})
        self.assertEqual([i.name for i in plan.definitions], ["p1", "p2", "p3"])
        self.assertEqual(loaded, ["t1", "t2"])

    def test_filter_shard_glob(self):
        plan, _ = self.load(filter_names=["t*"])
        self.assertEqual(plan.merges, {"t1": ["p1", "p2"], "t2": ["p3"]})
        plan, _ = self.load(filter_names=["*2"])
        self.assertEqual(plan.merges, {"t2": ["p3"]})

    def test_filter_part_glob_builds_without_merge(self):
        plan, _ = self.load(filter_names=["p[12]"])
        self.assertEqual(plan.merges, {})
        self.assertEqual([i.name for i in plan.definitions], ["p1", "p2"])

    def test_unmatched_pattern_warns(self):
        with self.assertLogs("pykmhelpers.core.utils", "WARNING") as logs:
            plan, _ = self.load(filter_names=["t1", "t3"])
        self.assertEqual(plan.merges, {"t1": ["p1", "p2"]})
        self.assertIn("No shard matches t3", logs.output[0])

    def test_no_match_is_refused(self):
        with self.assertRaisesRegex(ValueError, "No shard matches t3"):
            self.load(filter_names=["t3"])

    def test_filter_shard_name(self):
        plan, _ = self.load(filter_names=["t1"])
        self.assertEqual(plan.merges, {"t1": ["p1", "p2"]})
        self.assertEqual([i.name for i in plan.definitions], ["p1", "p2"])

    def test_filter_part_name_builds_without_merge(self):
        plan, _ = self.load(filter_names=["p2"])
        self.assertEqual(plan.merges, {})
        self.assertEqual([i.name for i in plan.definitions], ["p2"])

    def test_scripts_group_parts_under_their_shard(self):
        plan, _ = self.load()
        self.assertEqual(plan.scripts, {"p1": "t1", "p2": "t1", "p3": "t2"})
        self.assertEqual(plan.script_of("p2"), "t1")
        self.assertEqual(plan.script_of("unknown"), "unknown")

    def test_missing_shards(self):
        with self.assertRaises(ValueError):
            self.load({"type": "index_session", "shards": {}})

    def test_missing_shard_file(self):
        with self.assertRaises(FileNotFoundError):
            self.load({"shards": {"t": {"span": 1, "file": "shards/nope.yaml"}}})


class TestResolveInput(unittest.TestCase):
    """plan/apply/build INPUT: a file, a session, an index, a compose or design dir."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.design = self.tmp / "db"
        self.index = self.add_index("idx", ["s1", "s2"])

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def add_index(self, name, sessions):
        index = self.design / "compose" / name
        for session in sessions:
            (index / session / "shards").mkdir(parents=True)
            (index / session / "index.yaml").touch()
        with open(index / "layout.yaml", "w") as f:
            yaml.dump({"type": "layout", "data": {"sessions": sessions}}, f)
        return index

    def session_file(self, session):
        return str(self.index / session / "index.yaml")

    def test_a_file_is_used_as_is(self):
        shard = self.index / "s1" / "shards" / "idx_g0.yaml"
        shard.touch()
        self.assertEqual(resolve_input(str(shard)), str(shard))

    def test_session_dir(self):
        self.assertEqual(resolve_input(str(self.index / "s1")), self.session_file("s1"))

    def test_index_dir_takes_the_last_session(self):
        self.assertEqual(resolve_input(str(self.index)), self.session_file("s2"))

    def test_session_option(self):
        for path in (self.index, self.design / "compose", self.design):
            self.assertEqual(resolve_input(str(path), "s1"), self.session_file("s1"))

    def test_design_and_compose_dirs(self):
        self.assertEqual(resolve_input(str(self.design)), self.session_file("s2"))
        self.assertEqual(
            resolve_input(str(self.design / "compose")), self.session_file("s2")
        )

    def test_unknown_session_lists_the_sessions(self):
        with self.assertRaisesRegex(FileNotFoundError, "sessions: s1, s2"):
            resolve_input(str(self.design), "nope")

    def test_several_indexes_must_be_chosen(self):
        self.add_index("other", ["s1"])
        with self.assertRaisesRegex(ValueError, "several indexes"):
            resolve_input(str(self.design))
        self.assertEqual(resolve_input(str(self.index)), self.session_file("s2"))

    def test_no_index(self):
        empty = self.tmp / "empty"
        empty.mkdir()
        with self.assertRaises(FileNotFoundError):
            resolve_input(str(empty))

    def test_session_dir_of_a_shard_file(self):
        shard = self.index / "s1" / "shards" / "idx_g0.yaml"
        self.assertEqual(session_dir_of(str(shard)), str((self.index / "s1").resolve()))
        self.assertEqual(
            session_dir_of(self.session_file("s1")), str((self.index / "s1").resolve())
        )
        layout = LayoutStore.next_to(str(shard))
        self.assertEqual(layout._path, str((self.index / "layout.yaml").resolve()))


def write_layout(path, shards_per_span, span_partitions=0):
    """A layout whose spans 1, 2, ... hold the given shard names."""
    data = {
        "type": "layout",
        "data": {
            "base": 1.1,
            "map": {
                n: {
                    "name": f"idx_g{n - 1}",
                    "partition_count": span_partitions,
                    "shards": [{"name": sh, "samples": 3} for sh in shards],
                }
                for n, shards in enumerate(shards_per_span, start=1)
            },
        },
    }
    with open(path, "w") as f:
        yaml.dump(data, f)


def _record_in_process(path, shard, count):
    record_shard_partitions(path, shard, count)


class TestShardPartitions(unittest.TestCase):
    """apply records the partition count of a published shard in the layout;
    plan builds later parts of the shard with it."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.path = str(self.tmp / "layout.yaml")
        write_layout(self.path, [["idx_g0_p0", "idx_g0_p1"], ["idx_g1"]])

    def test_a_missing_count_is_recorded_per_shard(self):
        self.assertTrue(record_shard_partitions(self.path, "idx_g0_p0", 27))
        layout = LayoutStore(self.path)
        self.assertEqual(layout.shard_partition_count("idx_g0_p0"), 27)
        self.assertIsNone(layout.shard_partition_count("idx_g0_p1"))
        self.assertIsNone(layout.partition_count(1))  # the design is unchanged

    def test_a_recorded_count_is_never_changed(self):
        record_shard_partitions(self.path, "idx_g1", 17)
        before = Path(self.path).read_bytes()
        self.assertFalse(record_shard_partitions(self.path, "idx_g1", 17))
        with self.assertLogs(level="WARNING") as logs:
            self.assertFalse(record_shard_partitions(self.path, "idx_g1", 32))
        self.assertIn("layout left unchanged", logs.output[0])
        self.assertEqual(Path(self.path).read_bytes(), before)

    def test_unknown_shard_or_layout(self):
        with self.assertLogs(level="WARNING"):
            self.assertFalse(record_shard_partitions(self.path, "other", 8))
        self.assertFalse(record_shard_partitions(str(self.tmp / "none.yaml"), "idx_g1", 8))
        self.assertFalse(record_shard_partitions(self.path, "idx_g1", 0))

    def test_concurrent_publishes_keep_every_count(self):
        shards = [f"idx_g0_p{n}" for n in range(12)]
        write_layout(self.path, [shards])
        ctx = multiprocessing.get_context("fork")
        procs = [
            ctx.Process(target=_record_in_process, args=(self.path, sh, 8 + n))
            for n, sh in enumerate(shards)
        ]
        for p in procs:
            p.start()
        for p in procs:
            p.join()
        layout = LayoutStore(self.path)
        self.assertEqual(
            [layout.shard_partition_count(sh) for sh in shards],
            [8 + n for n in range(12)],
        )

    def test_the_published_count_wins_over_the_design_and_the_limits(self):
        write_layout(self.path, [["idx_g0"]], span_partitions=16)
        record_shard_partitions(self.path, "idx_g0", 27)
        config = make_config(limits='{"ram": 8000000000, "files": 4096, "threads": 4}')
        layout = LayoutStore(self.path)

        params = resolve_build_params(make_definition(partition_count=16), 7, config, layout, "idx_g0")
        self.assertEqual(params.partitions, 27)
        self.assertEqual(params.partitions_source, "published")

        # another shard of the span: the design
        params = resolve_build_params(make_definition(), 7, config, layout, "idx_g0_p1")
        self.assertEqual(params.partitions, 16)
        self.assertEqual(params.partitions_source, "design")

    def runner(self, registered):
        """A runner of a plan whose input sits next to the layout."""
        session = self.tmp / "initial"
        session.mkdir(exist_ok=True)
        (session / "index.yaml").write_text("type: index_session\n")
        runner = PlanRunner.__new__(PlanRunner)
        runner._input = str(session / "index.yaml")
        runner.state = SimpleNamespace(registered_partitions=lambda shard: registered)
        return runner

    def test_apply_records_the_registered_count(self):
        write_layout(self.path, [["idx_g0"]])
        self.runner(registered=32)._record_partitions({"shard": "idx_g0", "partitions": 27})
        self.assertEqual(LayoutStore(self.path).shard_partition_count("idx_g0"), 32)

    def test_apply_falls_back_on_the_plan_count(self):
        write_layout(self.path, [["idx_g0"]])
        self.runner(registered=None)._record_partitions({"shard": "idx_g0", "partitions": 27})
        self.assertEqual(LayoutStore(self.path).shard_partition_count("idx_g0"), 27)

    def test_a_rerun_of_apply_leaves_the_plan_fresh(self):
        """The layout is not a plan input: recording a count does not make
        the plan of pending jobs stale."""
        write_layout(self.path, [["idx_g0"], ["idx_g1"]])
        runner = self.runner(registered=None)
        plan = new_plan(runner._input, str(self.tmp), "initial", [runner._input], {}, {})
        runner._record_partitions({"shard": "idx_g0", "partitions": 27})
        check_fresh(plan, runner._input)
        runner._record_partitions({"shard": "idx_g0", "partitions": 27})
        self.assertIsNone(LayoutStore(self.path).shard_partition_count("idx_g1"))

    def test_a_recording_failure_does_not_fail_the_run(self):
        Path(self.path).write_text("{not yaml")
        with self.assertLogs(level="WARNING"):
            self.runner(registered=8)._record_partitions({"shard": "idx_g0", "partitions": 8})


class TestAlignWithStartedRuns(unittest.TestCase):
    """A part whose runs are already started keeps their partition count."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.paths = BuildPaths(str(self.tmp), "s1")
        self.executor = IndexExecutor.__new__(IndexExecutor)
        self.executor._paths = self.paths
        self.executor.has_index = lambda name: False

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def start_run(self, name, partitions):
        run = Path(self.paths.run(name))
        run.mkdir(parents=True)
        (run / "options.txt").write_text(
            f"Options: kmer_size=25, nb_parts={partitions}, minim_size=10"
        )

    def test_no_run_keeps_the_params(self):
        params = BuildParams(4, 32, None, 10)
        aligned = self.executor.align_with("t", params, "t_s1")
        self.assertEqual(aligned, params)
        self.assertEqual(aligned.partitions_source, "auto")

    def test_a_started_run_wins(self):
        self.start_run("t_s1", 16)
        aligned = self.executor.align_with("t", BuildParams(4, 32, None, 10), "t_s1")
        self.assertEqual(aligned.partitions, 16)
        self.assertEqual(aligned.partitions_source, "run")

    def test_the_registered_shard_wins(self):
        registered = SimpleNamespace(nb_partitions=16, minim_size=10)
        self.executor.has_index = lambda name: True
        self.executor._builder = SimpleNamespace(
            index=SimpleNamespace(get_index=lambda name: registered)
        )
        aligned = self.executor.align_with("t", BuildParams(4, 32, None, 10), "t_s1")
        self.assertEqual(aligned.partitions, 16)
        self.assertEqual(aligned.partitions_source, "registered")

    def test_a_started_chunk_wins(self):
        self.start_run("t_s1_chunk0", 8)
        aligned = self.executor.align_with("t", BuildParams(4, 32, None, 10), "t_s1")
        self.assertEqual(aligned.partitions, 8)


class TestChunks(unittest.TestCase):
    """A part is planned in one run, or in chunks of ``chunk_size`` samples."""

    def build(self, chunk_size):
        executor = IndexExecutor.__new__(IndexExecutor)
        executor._config = make_config()
        executor.run_names = []
        built = []
        executor._build_run = lambda name, fof, i, params: built.append(name)
        fof = FofManager(samples={f"s{n}": [f"s{n}.fa"] for n in range(5)})
        runs = executor.build(
            make_definition("t_s1"), fof, BuildParams(4, 8, chunk_size, 10)
        )
        return built, runs, executor.run_names

    def test_every_chunk_is_planned(self):
        built, runs, names = self.build(2)
        self.assertEqual(built, ["t_s1_chunk0", "t_s1_chunk1", "t_s1_chunk2"])
        self.assertEqual(runs, {"t_s1_chunk0": 2, "t_s1_chunk1": 2, "t_s1_chunk2": 1})
        self.assertEqual(names, built)

    def test_a_part_in_one_run(self):
        self.assertEqual(self.build(None)[0], ["t_s1"])


class TestJobNames(unittest.TestCase):
    chunks = [f"t_s1_chunk{n}" for n in range(7)]

    def test_one_job_per_task_by_default(self):
        self.assertEqual(
            job_names("t", self.chunks, True, 0), {"t": self.chunks + [PUBLISH]}
        )

    def test_fewer_chunks_than_per_job(self):
        self.assertEqual(job_names("t", self.chunks, True, 7), {"t": self.chunks + [PUBLISH]})

    def test_chunks_split_then_publish(self):
        jobs = job_names("t", self.chunks, True, 3)
        self.assertEqual(list(jobs), ["t_j0", "t_j1", "t_j2", "t_publish"])
        self.assertEqual(jobs["t_j2"], ["t_s1_chunk6"])
        self.assertEqual(jobs["t_publish"], [PUBLISH])

    def test_publish_only(self):
        self.assertEqual(job_names("t", [], True, 3), {"t": [PUBLISH]})


class TestTaskFilter(unittest.TestCase):
    """apply --task matches shards, tasks and jobs."""

    def setUp(self):
        self.runner = PlanRunner.__new__(PlanRunner)
        chunks = [f"_chunk{n}" for n in range(3)]
        self.runner._tasks = {
            f"{shard}_s1": {
                "shard": shard,
                "jobs": job_names(shard, [f"{shard}_s1{c}" for c in chunks], True, 1),
            }
            for shard in ("idx_g0", "idx_g1")
        }

    def names(self, *patterns):
        return [j.name for j in self.runner.jobs(list(patterns) or None)]

    def test_all(self):
        self.assertEqual(len(self.names()), 8)

    def test_a_shard_or_its_task_selects_all_its_jobs(self):
        expected = ["idx_g0_j0", "idx_g0_j1", "idx_g0_j2", "idx_g0_publish"]
        self.assertEqual(self.names("idx_g0"), expected)
        self.assertEqual(self.names("idx_g0_s1"), expected)

    def test_jobs(self):
        self.assertEqual(self.names("idx_g0_j1"), ["idx_g0_j1"])
        self.assertEqual(self.names("idx_g1_j*"), ["idx_g1_j0", "idx_g1_j1", "idx_g1_j2"])
        self.assertEqual(self.names("*_publish"), ["idx_g0_publish", "idx_g1_publish"])

    def test_no_match_is_refused(self):
        with self.assertRaisesRegex(ValueError, "No task matches"):
            self.names("nope*")


class TestPlanFile(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.definition = self.tmp / "index.yaml"
        self.definition.write_text("type: x\n")

    def plan(self):
        return new_plan(str(self.definition.resolve()), str(self.tmp), "s1", [str(self.definition)], {}, {})

    def test_round_trip(self):
        path = self.tmp / "assets" / "s1" / "plan.yaml"
        write_plan(str(path), self.plan())
        plan = load_plan(str(path))
        self.assertEqual(plan["session"], "s1")
        check_fresh(plan, str(self.definition))

    def test_changed_input_is_stale(self):
        plan = self.plan()
        self.definition.write_text("type: y\n")
        with self.assertRaisesRegex(ValueError, "inputs changed"):
            check_fresh(plan)

    def test_other_definition_is_stale(self):
        with self.assertRaisesRegex(ValueError, "made for"):
            check_fresh(self.plan(), str(self.tmp / "other.yaml"))

    def test_missing_plan(self):
        with self.assertRaisesRegex(FileNotFoundError, "kmhelpers plan"):
            load_plan(str(self.tmp / "nope.yaml"))


class TestBuildPaths(unittest.TestCase):
    def test_session_layout(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        definition = tmp / "compose" / "idx" / "upd" / "index.yaml"
        p = BuildPaths.for_input(str(tmp / "build"), str(definition))
        b = str((tmp / "build").resolve())
        self.assertEqual(p.session, "upd")
        shard = tmp / "compose" / "idx" / "upd" / "shards" / "idx_g0.yaml"
        self.assertEqual(BuildPaths.for_input(str(tmp / "build"), str(shard)).session, "upd")
        self.assertEqual(p.registry, b)
        self.assertEqual(p.shard("idx_g0"), f"{b}/idx_g0")
        self.assertEqual(p.run("idx_g0_upd"), f"{b}/work/upd/runs/idx_g0_upd")
        self.assertEqual(
            p.merge_step("idx_g0", "idx_g0__sub1_0"),
            f"{b}/work/upd/merges/idx_g0/idx_g0__sub1_0",
        )
        self.assertEqual(p.previous("idx_g0"), f"{b}/work/upd/previous/idx_g0")
        self.assertEqual(p.assets, f"{b}/assets/upd")
        self.assertEqual(p.lock, f"{b}/.registry.lock")

    def test_reserved_names(self):
        for name in ("work", "assets", "logs", ".hidden", "a/b"):
            with self.assertRaises(ValueError, msg=name):
                check_index_name(name)
        check_index_name("idx_g0")


class TestTargets(unittest.TestCase):
    def test_merges_and_own_targets(self):
        plan = WorkPlan(
            definitions=[make_definition(n) for n in ("a_s1", "b_s1", "c")],
            merges={"a": ["a_s1"], "b": ["b_s1", "b_s0"]},
        )
        self.assertEqual(
            IndexOps._targets(plan),
            {"a": ["a_s1"], "b": ["b_s1", "b_s0"], "c": ["c"]},
        )


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

    def test_one_script_per_run_and_publish_in_task_dirs(self):
        rec = ScriptRecorder(str(self.tmp))
        rec.select("b/b_p0")
        rec.add(f"build {self.tmp}/b_p0", "build b_p0")
        rec.select("a/a_p0")
        rec.add("build a_p0", "build a_p0")
        rec.select(ScriptRecorder.publish_group("b"))
        rec.add("merge b", "merge b_p0 -> b")
        written = rec.write(str(self.assets))

        header = [
            "#!/usr/bin/env bash",
            "set -euo pipefail",
            'ulimit -Sn "$(ulimit -Hn)" 2>/dev/null || true',
            f"export WORKDIR='{self.tmp}'",
            "cd ${WORKDIR}",
        ]
        ts = "$(date '+%F %T')"
        self.assertEqual(
            self.lines("b/b_p0.sh"),
            header
            + [
                f'echo "{ts} [b_p0] build b_p0"',
                "build ${WORKDIR}/b_p0",
                f'echo "{ts} [b_p0] done"',
            ],
        )
        self.assertEqual(
            self.lines("b/publish.sh"),
            header
            + [f'echo "{ts} [publish] merge b_p0 -> b"', "merge b", f'echo "{ts} [publish] done"'],
        )
        self.assertEqual(
            [Path(p).relative_to(self.assets).as_posix() for p in written],
            ["b/b_p0.sh", "a/a_p0.sh", "b/publish.sh"],
        )
        self.assertFalse((self.assets / "kmhelpers_apply.sh").exists())

    def test_add_requires_selection(self):
        with self.assertRaises(RuntimeError):
            ScriptRecorder(str(self.tmp)).add("cmd", "step")


if __name__ == "__main__":
    unittest.main()
