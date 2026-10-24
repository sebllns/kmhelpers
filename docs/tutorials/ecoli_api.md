# Tutorial: the Python API

This page runs the [E. coli tutorial](ecoli.md) and its
[update](ecoli_update.md) from Python. Each CLI command wraps a class of
`pykmhelpers`, and this page calls those classes directly:

| CLI | Python |
|---|---|
| [`list`](../commands/list.md) | `SampleLister` |
| [`profile`](../commands/profile.md) | `SpanProfiler` |
| [`compose`](../commands/compose.md) | `IndexComposer` |
| [`plan`](../commands/plan.md) | `IndexOps` with `ApplyMode.PLAN`, then `write_plan()` |
| [`apply`](../commands/apply.md) | `PlanRunner` |
| [`query`](../commands/query.md) | `QueryRunner` |

`design` and `build` are chains of these classes, written below as two small
functions. Parameters are the ones of the CLI tutorial, so both produce the same
`coli_db/` and `coli_build/` trees.

The complete script is
[`examples/tuto_ecoli_api.py`](https://github.com/sebllns/kmhelpers/blob/main/examples/tuto_ecoli_api.py):

```bash
python examples/tuto_ecoli_api.py my_workdir/
```

For more control over each step, see [Python API (advanced)](ecoli_api_advanced.md).

---

## Prerequisites

Same as the [E. coli tutorial](ecoli.md#prerequisites): **kmhelpers** installed,
with **kmindex** and **ntcard** on `PATH`.

The classes log through the standard `logging` module. Enable it to follow the
progress:

```python
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
```

---

## Step 1 - Download the dataset

Run the `wget` commands of [Step 1](ecoli.md#step-1-download-the-dataset) of the
CLI tutorial, or download from Python:

```python
import os
import urllib.request

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


def download(accessions, out_dir):
    """Download NCBI assemblies into out_dir, skipping files already there."""
    os.makedirs(out_dir, exist_ok=True)
    for acc in accessions:
        name = f"{os.path.basename(acc)}_genomic.fna.gz"
        path = os.path.join(out_dir, name)
        if not os.path.exists(path):
            urllib.request.urlretrieve(f"{NCBI}/{acc}/{name}", path)


download(DATASET, "coli_dataset")
```

??? abstract "I/O"
    **Input:** 10 NCBI FTP URLs  
    **Output:** `coli_dataset/`

---

## Step 2 - Design the index (`list` → `profile` → `compose`)

```python
from pykmhelpers.pipeline.composer import SESSION_FILE, IndexComposer, layout_path
from pykmhelpers.pipeline.index_db import IndexDB
from pykmhelpers.pipeline.sample_lister import SampleLister
from pykmhelpers.pipeline.span_profiler import SpanProfiler


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


definition = design("coli_dataset", "initial")
```

CLI equivalent: `kmhelpers design coli_dataset/ -o coli_db/ -n coli -s initial -k 25 -b 1.1 -g 2 --sb 0`

??? abstract "I/O"
    **Input:** `coli_dataset/`, scanned for sequence files (one sample per file)  
    **Output:** `coli_db/list/samples_initial.jsonl`, `coli_db/profile/` (profile.yaml, groups.png),
    `coli_db/compose/coli/` (`layout.yaml`, and the session `initial/index.yaml` with its `shards/`)

??? info "INFO"
    `IndexDB` keeps every index definition in a class-level registry keyed by
    name. The CLI runs each command in a new process; in a single Python process,
    free the names with `reset_index_registry()` before each compose, plan and apply.

??? question "Why scan a directory rather than pass a sample list?"
    A directory scan names each sample after its file and counts its k-mers.
    A sample list lets you set names, reuse k-mer counts, group files freely and
    mix locations - see [When to use a sample list](../commands/list.md#when-to-use-a-sample-list).

??? warning "API defaults"
    Some defaults of the classes differ from the CLI: `SampleLister` groups by
    leaf folder (`do_grouping=True`) and `SpanProfiler` uses `base=2.0`. Pass
    these parameters explicitly.

??? tip "Customize `SampleLister` (`list`)"
    | Parameter | CLI | Effect |
    |---|---|---|
    | `input_dir` / `input_list` | `INPUT` | Directory to scan, or a plain-text / YAML sample list |
    | `kmer_size` | `-k` | K-mer size used for counting |
    | `is_assembled` | `--dt` | `True`: distinct k-mers (assemblies); `False`: solid k-mers (raw reads) |
    | `do_count` | `--nc` | `False` skips ntcard |
    | `do_grouping` | `--lg` | One sample per leaf folder |
    | `pair_regex` | `-p, --paired` | Group mate files (R1/R2) into one sample; `DEFAULT_PAIR_REGEX` in `pykmhelpers.core.constants` |
    | `do_continue` | `-c` | Resume from an existing output file |
    | `autorename` | `-a` | Rename duplicate sample IDs instead of skipping them |
    | `ntcard_threads` | `--ntt` | Threads used by ntcard |

??? tip "Customize `SpanProfiler` (`profile`)"
    | Parameter | CLI | Effect |
    |---|---|---|
    | `n_groups` | `-g` | Number of storage-balanced groups (sub-indexes), `0` to choose it |
    | `base` | `-b` | Base of the span buckets: closer to 1 means finer buckets |
    | `false_positive_rate` | `--fp` | Bloom filter false-positive rate |
    | `no_grouping` | `--ngp` | One group, no grouping strategy |
    | `auto_group_*` | `--auto-group-*` | Limits of the automatic grouping (`n_groups=0`) |

??? tip "Customize `IndexComposer` (`compose`)"
    | Parameter | CLI | Effect |
    |---|---|---|
    | `profiles_file` / `layout_file` | `--pf` | New index from a profile, or update from the existing layout (`layout_path(compose_dir, name)`) |
    | `selected_profile` | `--pr` | Profile to use from `profile.yaml` (default: the one set by `profile`) |
    | `shard_budget` | `--sb` | Shard budget (`samples * base**span`), `0` for no sharding; `None`: the layout's rule on an update, the default budget otherwise |
    | `partition_count` | - | Partitions per index, `0` for automatic |
    | `minim_size` | `--minim-size` | Minimizer size, fixed for the life of the index |
    | `bitw`, `abundance_min` | `--ab` | Abundance bits (`0`: presence/absence) and minimum k-mer abundance |
    | `copy_list` | `--ncl` | `False` points the shards to the input sample list instead of a copy in the session |
    | `kmer_ratio` | `--kr` | Multiplies the k-mer ratio of the sample list |

---

## Step 3 - Build the index (`plan` → `apply`)

```python
from pykmhelpers.pipeline.index_ops import (
    ApplyMode,
    ApplyStatus,
    IndexOps,
    IndexOpsConfig,
)
from pykmhelpers.pipeline.index_ops.runner import PlanRunner


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


build(definition)
```

CLI equivalent: `kmhelpers build coli_db -s initial -o coli_build/ --cb 0`

??? abstract "I/O"
    **Input:** `coli_db/compose/coli/initial/index.yaml`  
    **Output:** `coli_build/index.json` + one folder per sub-index, `coli_build/coli_g0/`
    and `coli_build/coli_g1/`; the plan, `coli_build/assets/initial/plan.yaml`, with one
    directory of scripts per shard

??? info "INFO"
    `IndexOps` only plans: it takes every build decision (partitions, threads,
    chunks, merges, jobs) and `write_plan()` writes them. `PlanRunner` then runs the
    plan as it is. Both return an `ApplyResult`: `status` is `SUCCESS`, `PARTIAL`
    (some indexes failed, only with `fail_on_error=False`), `FAILED` or `NONE`
    (nothing to do), and `details` holds the per-index report the CLI writes to
    `coli_build/logs/`.

    The publish step of each shard runs `kmhelpers manage check --shard <shard>`
    before deleting what built it: a structure check, then a query of a few
    k-mers of the shard's first sample (see [manage - check](../commands/manage.md#check)).

??? tip "Customize `IndexOpsConfig` (`plan`)"
    | Parameter | CLI | Effect |
    |---|---|---|
    | `limits`, `safety_margin` | `--limits`, `--safety-margin` | Resource limits (`ram`, `files`, `threads`) and the fraction of detected limits to use |
    | `chunk_budget` | `--cb` | K-mer budget of one kmtricks chunk, `0` for no limit |
    | `max_chunks` | `--max-chunks` | Cap on the chunks one shard is built in |
    | `chunks_per_job` | `--cpj` | Chunks one job builds, `0` for one job per shard |
    | `filter_names` | `--sh` | Plan only these shards (names or glob patterns) |
    | `kmindex_skip_compression` | `--ncp` | Do not compress intermediate files |
    | `keep_previous` | `--keep-previous` | Keep the replaced version of an updated index |
    | `sample_rootpath` | `--bp` | Base path for relative sample paths |

    `ApplyMode.DRY_RUN` plans without checking that the sample files exist
    (`--offline`). `runner.run(..., show_progress=True)` is `--show-progress`, and
    `runner.jobs(["coli_g0"])` selects jobs as `apply --task` does.

---

## Step 4 - Query the index (`query`)

Extract the first contig of `GCA_000780515`, then query it:

```python
import gzip

from pykmhelpers import QueryRunner, QueryRunnerConfig


def first_contig(fasta_gz, out_file):
    """Write the first sequence of a gzipped FASTA file to out_file."""
    with gzip.open(fasta_gz, "rt") as fin, open(out_file, "w") as fout:
        for n, line in enumerate(fin):
            if line.startswith(">") and n > 0:
                break
            fout.write(line)


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


first_contig("coli_dataset/GCA_000780515.1_ASM78051v1_genomic.fna.gz", "query.fa")
print(query("query.fa", "results"))
```

CLI equivalent: `kmhelpers query -r coli_build/ -o results/ query.fa`

??? abstract "I/O"
    **Input:** `coli_build/`, `query.fa`  
    **Output:** `results/query/` (`results.tsv`, statistics, raw kmindex output),
    and the results as Python objects

??? success "RESULT"
    ```python
    {'GCA_000780515_1_ASM78051v1_genomic': 1.0}
    ```

    `run()` returns, per query file, one `KmindexQueryResult` per sub-index.
    Their `items` are `{index: {query: {sample: score}}}`, the scores of
    `results/query/results.tsv`. To merge and summarize them, see
    [advanced](ecoli_api_advanced.md#merge-and-summarize-results).

??? tip "Customize `QueryRunnerConfig` (`query`)"
    | Parameter | CLI | Effect |
    |---|---|---|
    | `index_ids` | `--sh` | Query only these shards |
    | `zvalue` | `-z` | Findere z: effective false-positive rate p^z |
    | `threshold` | `--thr` | Minimum score kept |
    | `threads` | `-t` | kmindex threads |
    | `batch`, `single_query` | `--bq`, `-s` | Concatenate files or sequences into one query |
    | `output_format`, `export` | `-f`, `-x` | Data format (`tsv`, `json`, `yaml`, `None`) and human report (`md`, `html`) |
    | `on_existing`, `force` | `-e` | Existing output directory: `skip` (default, returns no result), `fail`, `delete` |
    | `stats` | `--stats` | Write `sequence_stats.tsv` and `sample_stats.tsv` |
    | `on_result` | - | Callback called with each query's results, see [advanced](ecoli_api_advanced.md#stream-query-results) |

---

## Update the index

As in [Update an existing index](ecoli_update.md): download the new sample into
its own directory, design an `update` session against the existing layout
(no `profile` step), and build it into the same `coli_build/`.

```python
UPDATE = ["000/005/845/GCA_000005845.2_ASM584v2"]

download(UPDATE, "coli_update")
definition = design("coli_update", "update", profile=False)
build(definition)

first_contig("coli_update/GCA_000005845.2_ASM584v2_genomic.fna.gz", "query_update.fa")
print(query("query_update.fa", "results_update"))
print(query("query.fa", "results_after"))
```

CLI equivalent: `kmhelpers design coli_update/ -o coli_db/ -n coli -s update`,
then `kmhelpers build coli_db -s update -o coli_build/ --cb 0`

??? success "RESULT"
    The new sample scores **1.0** on its own contig, and `GCA_000780515` still
    scores **1.0** on `query.fa`. `coli_g0` now holds 6 samples.
