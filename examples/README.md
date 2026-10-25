# Examples

Runnable scripts of the kmhelpers pipeline (`design -> build -> query -> update`).
Run them from the repository root. Unless said otherwise, they need `kmhelpers`,
`kmindex` and `ntcard` on `PATH`.

| Script | What it shows | Data | Run it |
|---|---|---|---|
| [`mini_e2e.sh`](mini_e2e.sh) | Shortest tour: design, build, query, update, query | 10 small random FASTA | `bash examples/mini_e2e.sh [WORKDIR]` |
| [`pipeline_cli.sh`](pipeline_cli.sh) | The same steps through the CLI, checking that each query finds its sample (score >= 0.9) | random FASTA | `bash examples/pipeline_cli.sh` |
| [`pipeline_api.py`](pipeline_api.py) | The same steps through the Python API (`SampleLister`, `SpanProfiler`, `IndexComposer`, `IndexOps`, `QueryRunner`) | random FASTA | `python examples/pipeline_api.py` |
| [`tuto_ecoli_e2e.sh`](tuto_ecoli_e2e.sh) | The [E. coli tutorial](https://sebllns.github.io/kmhelpers/tutorials/ecoli/), end to end | 10 NCBI assemblies (downloaded, needs `wget`) | `bash examples/tuto_ecoli_e2e.sh [WORKDIR]` |
| [`tuto_ecoli_api.py`](tuto_ecoli_api.py) | The [E. coli tutorial with the Python API](../docs/tutorials/ecoli_api.md) | 10 NCBI assemblies (downloaded) | `python examples/tuto_ecoli_api.py [WORKDIR]` |
| [`large_plan_offline.sh`](large_plan_offline.sh) | How a large collection is split into groups and shards, and the build scripts `plan` writes. Nothing is built | fake sample list, no sequences (needs only `kmhelpers`) | `bash examples/large_plan_offline.sh [WORKDIR]` |

## Working directory

- Scripts that take `[WORKDIR]` work there, or in a new temporary directory when it is left out. They print the path they use.
- `pipeline_cli.sh` works in `./examples_cli`, which it **removes and recreates** on each run.
- `pipeline_api.py` works in a new temporary directory.

## Reproducibility

`mini_e2e.sh` and `pipeline_cli.sh` set `KMHELPERS_SEED=42`, so they create the same samples on every run.
`pipeline_api.py` uses `KMHELPERS_SEED` only when you set it: `KMHELPERS_SEED=42 python examples/pipeline_api.py`.

## Continuous integration

`pipeline_cli.sh`, `pipeline_api.py` and `large_plan_offline.sh` run in [`tests.yml`](../.github/workflows/tests.yml), and
`tuto_ecoli_e2e.sh` runs in [`tutorial.yml`](../.github/workflows/tutorial.yml). Keep them working
when you change the CLI or the API.

## `data/`

`data/SYNTHETIC_ROD_10.tar` is a small prebuilt kmtricks index used by `pykmhelpers/tests/test_index.py`.
The tests extract it to `data/SYNTHETIC_ROD_10/` (git-ignored) when it is missing.
