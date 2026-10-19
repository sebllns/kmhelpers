# Python API (advanced)

This page extends the [Python API tutorial](ecoli_api.md) without changing
kmhelpers: the pipeline steps exchange plain files (JSONL sample list,
`profile.yaml`, layout and index definitions, build scripts), so any step can be
replaced, fed with your own data or post-processed. The snippets run in the
tutorial's working directory, next to `coli_dataset/`, `coli_db/` and
`coli_build/`, and reuse its `reset_index_registry()` and `build()` functions.

---

## Bypass the automatic listing

`SampleLister` scanning a directory names each sample after its file and counts
its k-mers. To control names, grouping, locations or counts, give it a sample list,
or write its JSONL output yourself. See
[When to use a sample list](../commands/list.md#when-to-use-a-sample-list).

### Generate a sample list from metadata

Name samples after a metadata table instead of their file names:

```python
import os

from pykmhelpers.pipeline.sample_lister import SampleLister

strains = {
    "GCA_000780515.1_ASM78051v1": "strain_A",
    "GCA_001076125.1_ASM107612v1": "strain_B",
    "GCA_001417575.1_ASM141757v1": "strain_C",
}
with open("strains.txt", "w") as f:
    for accession, strain in strains.items():
        f.write(f"{strain} coli_dataset/{accession}_genomic.fna.gz\n")

os.makedirs("strains_db/list", exist_ok=True)
SampleLister(
    output_file="strains_db/list/strains.jsonl",
    input_list="strains.txt",
    kmer_size=25,
    do_grouping=False,
).run()
```

??? success "RESULT"
    ```json
    {"name": "strain_A", "files": ["coli_dataset/GCA_000780515.1_ASM78051v1_genomic.fna.gz"], "kmer_count": 10898876}
    ```

Each line is `[sample_id] file_1[,file_2,...] [kmer_count]`: list several
comma-separated files to group them into one sample, and add a count to skip
ntcard. Relative paths are resolved from the directory of the list file. See
[Input formats](../commands/list.md#input-formats).

### Write the JSONL yourself

The JSONL file is the contract between `list` and the next steps: a header line
with the k-mer size, then one `{"name", "files", "kmer_count"}` object per sample.
Writing it directly skips `SampleLister`, for example to reuse k-mer counts
computed by another tool or an earlier run:

```python
import json

with open("coli_db/list/coli_samples_initial.jsonl") as f:
    counted = [json.loads(line) for line in f][1:]

os.makedirs("reuse_db/list", exist_ok=True)
with open("reuse_db/list/reuse.jsonl", "w") as f:
    f.write(json.dumps({"k": 25, "assembled": True, "abundance_min": 1}) + "\n")
    for s in counted:
        path = os.path.abspath(os.path.join("coli_dataset", s["files"][0]))
        entry = {"name": s["name"], "files": [path], "kmer_count": s["kmer_count"]}
        f.write(json.dumps(entry) + "\n")
```

??? info "INFO"
    - `k` is required in the header; `assembled` and `abundance_min` are written
      by `list` and kept for consistency.
    - Use absolute file paths when the JSONL is not written by `list`.
    - `kmer_count` must be positive: it sizes the Bloom filter of the sample.
      For raw reads, count solid k-mers (seen at least twice), as `list` does
      with `is_assembled=False`.

---

## Filter samples between steps

Load the JSONL, keep or rename samples, write it back, then continue with
`SpanProfiler` and `IndexComposer`. Here, small assemblies are left out:

```python
from pykmhelpers.pipeline.composer import IndexComposer
from pykmhelpers.pipeline.span_profiler import SpanProfiler

with open("reuse_db/list/reuse.jsonl") as f:
    header, *samples = [json.loads(line) for line in f]

kept = [s for s in samples if s["kmer_count"] >= 5_000_000]
with open("reuse_db/list/reuse.jsonl", "w") as f:
    for entry in [header, *kept]:
        f.write(json.dumps(entry) + "\n")

SpanProfiler(
    input_file="reuse_db/list/reuse.jsonl",
    output_dir="reuse_db/profile",
    n_groups=2,
    base=1.1,
).run()
reset_index_registry()
IndexComposer(profiles_file="reuse_db/profile/profile.yaml", name="reuse").run(
    input_file="reuse_db/list/reuse.jsonl",
    output_dir="reuse_db/compose",
    run_id="initial",
)
```

??? success "RESULT"
    7 of the 10 samples are kept, and `reuse_db/compose/reuse/initial/reuse.yaml`
    is ready to build.

The same applies to the other files: `profile.yaml` (see
[profile](../commands/profile.md)) and the index definitions (see
[compose](../commands/compose.md)) are plain YAML that can be reviewed or edited
before the next step.

---

## Run the build outside Python

`ApplyMode.PLAN` generates the commands without running them, and
`write_script()` saves them as bash scripts. Plan from Python, then run the build
where and when you want: another machine with the same paths, a job scheduler,
or after review.

```python
from pykmhelpers.pipeline.index_ops import ApplyMode, IndexOps, IndexOpsConfig

reset_index_registry()
ops = IndexOps(IndexOpsConfig(workdir="reuse_build", kmindex_threads=4))
result = ops.run("reuse_db/compose/reuse/initial/reuse.yaml", mode=ApplyMode.PLAN)
ops.write_script()
print(result.status)
```

```bash
ls reuse_build/assets/initial/
# kmhelpers_apply.sh  reuse_g0_initial.sh  reuse_g0_initial_merge.sh  ...
bash reuse_build/assets/initial/kmhelpers_apply.sh
```

??? info "INFO"
    There is one `<part>.sh` script per group of parts (the kmindex builds), one
    `<part>_merge.sh` (publication into the registry and cleanup), and
    `kmhelpers_apply.sh` running them all in order. Each script stops at the
    first failing command. See [plan](../commands/plan.md).

---

## Stream query results

`QueryRunnerConfig(on_result=...)` calls a function with the results of each
query file as soon as it completes, without waiting for the other files or
reading the output files. Results come as one `KmindexQueryResult` per
sub-index, with `items` as `{index: {query: {sample: score}}}`:

```python
from pykmhelpers import QueryRunner, QueryRunnerConfig

best = {}


def keep_best(results):
    """Keep the best sample of each query sequence, over all sub-indexes."""
    for result in results:
        for queries in result.items.values():
            for query, samples in queries.items():
                for sample, score in samples.items():
                    if score > best.get(query, ("", 0.0))[1]:
                        best[query] = (sample, score)


QueryRunner(
    QueryRunnerConfig(
        registry_path="coli_build",
        output_dir="results_stream",
        output_format=None,  # keep only the raw kmindex output
        on_result=keep_best,
    )
).run(["query.fa", "query_update.fa"])
print(best)
```

??? success "RESULT"
    ```python
    {'JSPL01000060.1': ('GCA_000780515_1_ASM78051v1_genomic', 1.0),
     'U00096.3': ('GCA_000005845_2_ASM584v2_genomic', 1.0)}
    ```

### Merge and summarize results

The CLI merges the sub-indexes by loading every raw output file of a query into
one `KmindexQueryResult`. Do the same to use its statistics and formats:

```python
import glob

from pykmhelpers import KmindexQueryResult

merged = KmindexQueryResult()
for path in glob.glob("results_stream/query_update/kmindex_output/*.jsonl"):
    merged.load_jsonl(path)

merged.match_stats(threshold=0.5)   # one row per query sequence
merged.sample_stats(threshold=0.8)  # one row per matched sample
merged.convert("json", threshold=0.8)  # also "tsv", "yaml"
```

??? success "RESULT"
    `sample_stats(threshold=0.8)` keeps 2 samples: `GCA_000005845` (1.0) and
    `GCA_000938575` (0.87), a close relative of the K-12 reference.

---

## Stability

The classes, parameters and files used on this page are the public interface.
Methods starting with `_` are internal and may change between versions; if a
customization needs one, please open an
[issue](https://github.com/sebllns/kmhelpers/issues).
