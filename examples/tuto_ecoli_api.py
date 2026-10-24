#!/usr/bin/env python3
"""E. coli tutorial with the Python API (docs/tutorials/ecoli_api.md).

Same steps as tuto_ecoli_e2e.sh: download 10 assemblies, design, build and
query an index, then add one sample to it. Requires kmindex and ntcard on PATH.

Usage: python tuto_ecoli_api.py [WORKDIR]
"""

import gzip
import logging
import os
import sys
import tempfile
import urllib.request

from pykmhelpers import QueryRunner, QueryRunnerConfig
from pykmhelpers.pipeline.composer import SESSION_FILE, IndexComposer, layout_path
from pykmhelpers.pipeline.index_db import IndexDB
from pykmhelpers.pipeline.index_ops import (
    ApplyMode,
    ApplyStatus,
    IndexOps,
    IndexOpsConfig,
)
from pykmhelpers.pipeline.index_ops.runner import PlanRunner
from pykmhelpers.pipeline.sample_lister import SampleLister
from pykmhelpers.pipeline.span_profiler import SpanProfiler

NCBI = "https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA"
DATASET = [
    "000/780/515/GCA_000780515.1_ASM78051v1",
    "001/076/125/GCA_001076125.1_ASM107612v1",
    "001/417/575/GCA_001417575.1_ASM141757v1",
    "000/944/435/GCA_000944435.1_Ec57A_E8C1_MIRA_assembly",
    "001/075/925/GCA_001075925.1_ASM107592v1",
    "000/936/715/GCA_000936715.1_E8C1_assembly",
    "000/939/215/GCA_000939215.1_Ec57A_A7_MIRA_assembly",
    "001/413/795/GCA_001413795.1_ASM141379v1",
    "001/373/195/GCA_001373195.1_57A_A7_assembly",
    "000/938/575/GCA_000938575.1_D1C4_assembly",
]
UPDATE = ["000/005/845/GCA_000005845.2_ASM584v2"]


def download(accessions, out_dir):
    """Download NCBI assemblies into out_dir, skipping files already there."""
    os.makedirs(out_dir, exist_ok=True)
    for acc in accessions:
        name = f"{os.path.basename(acc)}_genomic.fna.gz"
        path = os.path.join(out_dir, name)
        if not os.path.exists(path):
            urllib.request.urlretrieve(f"{NCBI}/{acc}/{name}", path)


def first_contig(fasta_gz, out_file):
    """Write the first sequence of a gzipped FASTA file to out_file."""
    with gzip.open(fasta_gz, "rt") as fin, open(out_file, "w") as fout:
        for n, line in enumerate(fin):
            if line.startswith(">") and n > 0:
                break
            fout.write(line)


def reset_index_registry():
    """Free the index names held by IndexDB, a process-wide registry.

    Compose and build each create IndexDB objects named after the indexes;
    a second one with the same name in the same process raises an error.
    """
    for db in IndexDB.get_all() or []:
        if db.name:
            IndexDB.remove_instance(db.name)


def design(input_dir, session, profile=True):
    """list -> profile -> compose, the steps of `kmhelpers design`."""
    jsonl = f"coli_db/list/samples_{session}.jsonl"
    os.makedirs("coli_db/list", exist_ok=True)

    # list: one sample per file, k-mers counted with ntcard
    SampleLister(
        output_file=jsonl,
        input_dir=input_dir,
        kmer_size=25,
        is_assembled=True,
        do_grouping=False,
    ).run()

    # profile: Bloom filter spans, split into 2 groups (initial session only)
    if profile:
        SpanProfiler(
            input_file=jsonl,
            output_dir="coli_db/profile",
            n_groups=2,
            base=1.1,
        ).run()

    # compose: a new index from the profile, or an update from the layout
    # (coli_db/compose/coli/layout.yaml, written by the first session)
    reset_index_registry()
    IndexComposer(
        profiles_file="coli_db/profile/profile.yaml" if profile else None,
        layout_file=None if profile else layout_path("coli_db/compose", "coli"),
        name="coli",
        # no sharding, as `--sb 0`: each group is one index, coli_g0 and coli_g1
        shard_budget=0 if profile else None,
    ).run(input_file=jsonl, output_dir="coli_db/compose", run_id=session)
    return f"coli_db/compose/coli/{session}/{SESSION_FILE}.yaml"


def build(definition):
    """plan -> apply, the steps of `kmhelpers build`."""
    # plan: one kmtricks run per shard (chunk_budget=0, as `--cb 0`)
    reset_index_registry()
    ops = IndexOps(IndexOpsConfig(workdir="coli_build", chunk_budget=0))
    result = ops.run(definition, mode=ApplyMode.PLAN)
    assert result.status is ApplyStatus.SUCCESS, f"plan: {result.status.value}"
    # coli_build/assets/<session>/plan.yaml and the scripts of its jobs
    ops.write_plan()

    # apply: run every job of the plan, here
    reset_index_registry()
    runner = PlanRunner("coli_build", definition)
    result = runner.run(runner.jobs(), fail_on_error=True)
    assert result.status is ApplyStatus.SUCCESS, f"apply: {result.status.value}"


def query(query_file, output_dir):
    """Query the index, return {sample: best score}."""
    runner = QueryRunner(
        QueryRunnerConfig(
            registry_path="coli_build",
            output_dir=output_dir,
            output_format="tsv",
        )
    )
    scores = {}
    for result in runner.run([query_file])[0]:
        for queries in result.items.values():
            for samples in queries.values():
                for sample, score in samples.items():
                    scores[sample] = max(scores.get(sample, 0.0), score)
    return scores


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    workdir = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp()
    os.makedirs(workdir, exist_ok=True)
    os.chdir(workdir)
    print(f"Working directory: {os.getcwd()}")

    # Step 1: download the dataset
    download(DATASET, "coli_dataset")

    # Step 2: design the index
    definition = design("coli_dataset", "initial")

    # Step 3: build the index
    build(definition)

    # Step 4: query the first contig of GCA_000780515
    first_contig("coli_dataset/GCA_000780515.1_ASM78051v1_genomic.fna.gz", "query.fa")
    scores = query("query.fa", "results")
    print(f"Initial: {scores}")
    assert scores.get("GCA_000780515_1_ASM78051v1_genomic") == 1.0

    # Update: add one sample, in its own directory so only it is listed
    download(UPDATE, "coli_update")
    definition = design("coli_update", "update", profile=False)
    build(definition)

    first_contig(
        "coli_update/GCA_000005845.2_ASM584v2_genomic.fna.gz", "query_update.fa"
    )
    scores = query("query_update.fa", "results_update")
    print(f"Update: {scores}")
    assert scores.get("GCA_000005845_2_ASM584v2_genomic") == 1.0

    scores = query("query.fa", "results_after")
    assert scores.get("GCA_000780515_1_ASM78051v1_genomic") == 1.0
    print("All queries matched.")


if __name__ == "__main__":
    main()
