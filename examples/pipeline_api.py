#!/usr/bin/env python3
"""End-to-end kmhelpers pipeline via the Python API.

Mirrors pykmhelpers/tests/test_pipeline_e2e.py (TestDesignBuildQueryUpdateQuery):
    design -> build -> query -> update -> query

Each CLI command wraps a pipeline class; this script calls those classes
directly (list=SampleLister, profile=SpanProfiler, compose=IndexComposer,
plan/apply=IndexOps, query=QueryRunner). Random FASTA is generated with
Fasta.create_random_test_dataset (the same helper behind `kmhelpers test
create-fasta`). Queries feed a whole indexed sample back, so it scores ~1.0.

Unlike the CLI (a fresh process per command), this runs in one process, so it
must reset the process-global IndexDB registry between compose/build calls (see
reset_index_registry). Requires kmindex and ntcard on PATH.
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

from pykmhelpers import Fasta, QueryRunner, QueryRunnerConfig
from pykmhelpers.core.byte import ByteCounter
from pykmhelpers.pipeline.composer import IndexComposer
from pykmhelpers.pipeline.index_db import IndexDB
from pykmhelpers.pipeline.index_ops import (
    ApplyMode,
    ApplyStatus,
    IndexOps,
    IndexOpsConfig,
)
from pykmhelpers.pipeline.sample_lister import SampleLister
from pykmhelpers.pipeline.span_profiler import SpanProfiler

KMER_SIZE = 21
MIN_SCORE = 0.9


def reset_index_registry():
    """Free every name held in the class-level IndexDB registry.

    IndexDB keeps a strong, class-level reference to each instance keyed by
    name, so re-creating an index of the same name raises "already exists in
    IndexDB". The CLI avoids this with a fresh process per command; here we pop
    the names before each compose/build to get the same isolation.
    """
    for db in list(IndexDB.get_all() or []):
        IndexDB.remove_instance(db.name)


def build(reg, workdir):
    """Plan then apply a definition file into workdir (mirrors `kmhelpers build`)."""
    reset_index_registry()
    # basename of the definition's parent dir (initial / upd) keeps the two
    # builds' bloom directories distinct.
    defn_dir = os.path.basename(os.path.dirname(os.path.realpath(reg)))
    iops = IndexOps(
        config=IndexOpsConfig(
            workdir=workdir,
            index_data_folder=os.path.join(workdir, "kmindex_data", defn_dir),
            registry_dir=workdir,
            minimizer_length=10,
            on_existing="fail",
            safety_margin=0.75,
        )
    )
    iops.run(reg, mode=ApplyMode.PLAN, fail_on_error=False)
    iops.write_script()
    result = iops.run(reg, mode=ApplyMode.APPLY, fail_on_error=True)
    assert result.status is not ApplyStatus.FAILED, f"build failed: {result.status}"


def query(sample_file, workdir, output_dir):
    """Query one FASTA file against the registry (mirrors `kmhelpers query`)."""
    QueryRunner(
        QueryRunnerConfig(
            registry_path=workdir,
            output_dir=output_dir,
            output_format="json",
            zvalue=6,
            threshold=0.05,
        )
    ).run([sample_file])


def load_query_results(results_dir):
    """Merge every <results_dir>/<query>/result/*.jsonl into {query: {sample: frac}}."""
    merged = {}
    for jf in sorted(Path(results_dir).rglob("*.jsonl")):
        if jf.parent.name != "result":
            continue
        for line in jf.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            merged.setdefault(rec["query"], {}).update(rec["samples"])
    return merged


def assert_query_hit(results_dir, sample, min_score=MIN_SCORE):
    merged = load_query_results(results_dir)
    score = max((s.get(sample, 0.0) for s in merged.values()), default=0.0)
    assert score >= min_score, (
        f"FAIL: {sample} scored {score} (< {min_score}) in {results_dir}"
    )
    print(f"OK: {sample} scored {score:.3f} in {results_dir}")


def main():
    workdir = tempfile.mkdtemp(prefix="kmhelpers_api_")
    try:
        os.chdir(workdir)
        print(f"Working directory: {workdir}")

        # 1. Generate 5 samples -> data/data_0.fasta .. data_4.fasta.
        Fasta.create_random_test_dataset(
            output_dir="data", n_samples=5, average_size=3000, min_size=2500
        )

        # 2. Design: list -> profile -> compose.
        os.makedirs("db/list", exist_ok=True)
        SampleLister(
            output_file="db/list/idx.jsonl",
            input_dir="data",
            kmer_size=KMER_SIZE,
            is_assembled=True,
            do_count=True,
            do_grouping=False,
        ).run()
        SpanProfiler(
            input_file="db/list/idx.jsonl",
            output_dir="db/profile",
            n_groups=1,
            base=1.1,
        ).run()
        reset_index_registry()
        IndexComposer(
            profiles_file="db/profile/profile.yaml",
            name="idx",
            bf_max_size=ByteCounter.from_str("512GB"),
            partition_min_size=ByteCounter.from_str("4GB"),
        ).run(
            input_file="db/list/idx.jsonl",
            output_dir="db/compose",
            run_id="initial",
        )

        # 3. Build (plan -> apply).
        build("db/compose/idx/initial/idx.yaml", "build")

        # 4. Query a sample against its own index -> perfect hit.
        query("data/data_0.fasta", "build", "results")
        assert_query_hit("results", "data_0")

        # 5. Update: a new, smaller sample (distinct name update_0), composed
        #    against the existing layout (no profiles_file) and rebuilt in place.
        Fasta.create_random_test_dataset(
            output_dir="update", n_samples=1, average_size=2000, min_size=1800
        )
        SampleLister(
            output_file="db/list/upd.jsonl",
            input_dir="update",
            kmer_size=KMER_SIZE,
            is_assembled=True,
            do_count=True,
            do_grouping=False,
        ).run()
        reset_index_registry()
        IndexComposer(
            layout_file="db/compose/idx_layout.yaml",
            name="idx",
        ).run(
            input_file="db/list/upd.jsonl",
            output_dir="db/compose",
            run_id="upd",
        )
        build("db/compose/idx/upd/idx.yaml", "build")

        # 6. The new sample is queryable, and the original still matches.
        query("update/update_0.fasta", "build", "results_upd")
        assert_query_hit("results_upd", "update_0")

        query("data/data_0.fasta", "build", "results_after")
        assert_query_hit("results_after", "data_0")

        print("All queries matched. Pipeline complete.")
    finally:
        os.chdir("/")
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())