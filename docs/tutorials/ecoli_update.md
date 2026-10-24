# Update an existing index: [design](../commands/design.md) → [build](../commands/build.md)

This page is a companion to the [E. coli tutorial](ecoli.md). It shows how to add
samples to an index that already exists, without rebuilding it from scratch. It
assumes you have already followed the main steps and have `coli_db/` and
`coli_build/` on disk.

---

## Step 1 - Download a new sample

Download it into its own directory, `coli_update/`: `design` scans the whole
directory, and the samples already indexed must **not** be listed again.

```bash
mkdir -p coli_update && cd coli_update
wget "https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/000/005/845/GCA_000005845.2_ASM584v2/GCA_000005845.2_ASM584v2_genomic.fna.gz"
cd ..
```

??? abstract "I/O"
    **Input:** one NCBI FTP URL (*E. coli* K-12 MG1655 reference assembly)  
    **Output:** `coli_update/GCA_000005845.2_ASM584v2_genomic.fna.gz`

---

## Step 2 - Design the update session ([`design`](../commands/design.md))

Re-run `design` with the same `-o` and `-n` as
[Step 2](ecoli.md#step-2-design-the-index-design) of the tutorial, and a fresh
`-s` session ID:

```bash
kmhelpers design coli_update/ -o coli_db/ -n coli -s update
```

??? abstract "I/O"
    **Input:** `coli_update/`, existing layout `coli_db/compose/coli/layout.yaml`  
    **Output:** `coli_db/compose/coli/update/index.yaml`

??? note "Options"
    | Option | Meaning |
    |--------|---------|
    | `coli_update/` | INPUT: the directory of the new sample files, scanned |
    | `-o coli_db/`, `-n coli` | the design directory and index of the first session |
    | `-s update` | a new session, under a name of your choice (`update` here, a date or a batch name as well): its samples are added to the existing sub-indexes |

    Not set here, and not to be: `-k`, `-b`, `-g` and `--sb` come from the layout of the index (`coli_db/compose/coli/layout.yaml`), so the update fits the existing sub-indexes.

??? info "INFO"
    `design` detects the existing layout file at `coli_db/compose/coli/layout.yaml`,
    skips the [`profile`](../commands/profile.md) step, and composes only the new
    samples. The k-mer size, span base and grouping of the initial run are reused,
    so the new sub-indices stay compatible with the existing ones.

---

## Step 3 - Build the update session ([`build`](../commands/build.md))

Build into the **same** `BUILD_DIR` as
[Step 3](ecoli.md#step-3-build-the-index-build) of the tutorial:

```bash
kmhelpers build coli_db -s update -o coli_build/ --cb 0 --show-progress
```

??? abstract "I/O"
    **Input:** `coli_db/compose/coli/update/index.yaml`  
    **Output:** updated `coli_g0` in `coli_build/coli_g0/`, updated
    `coli_build/index.json`

??? note "Options"
    | Option | Meaning |
    |--------|---------|
    | `coli_db`, `-s update` | the design directory, and the session to build |
    | `-o coli_build/` | the same index directory as the first build: the new samples are merged into its sub-indexes |
    | `--cb 0` | no chunk budget: one kmtricks run per shard (see [build - Shards and chunks](../commands/build.md#shards-and-chunks)) |
    | `--show-progress` | one line per shard: progress bar, step running, end status |

??? info "INFO"
    Each index keeps its folder, `coli_build/<name>/`. While the session is
    built, its runs and merges live in `coli_build/work/update/`, deleted at the
    end. Building the same session again resumes it, or does nothing if it
    finished.

    Building a session into a `BUILD_DIR` that already holds the index triggers a
    merge. `kmindex` cannot add samples to an existing index in place, so the
    update merges the old and the new samples into a new index, which replaces
    the previous one in `coli_build/coli_g0/`: it now holds its initial samples
    plus the new one. The previous version is deleted once the new one is
    checked (`--keep-previous` keeps it in `coli_build/work/update/previous/`).

    `GCA_000005845` falls in the span bucket of `coli_g0`, so only that
    sub-index is merged. `coli_g1` is untouched.

??? warning "Disk space"
    The previous version and the updated one coexist on disk during the merge.
    Plan for at least twice the size of the sub-indices being updated.

---

## Step 4 - Query the updated index ([`query`](../commands/query.md))

```bash
kmhelpers query -r coli_build/ -o results_update/ query.fa
```

??? note "Options"
    | Option | Meaning |
    |--------|---------|
    | `-r coli_build/` | the updated index directory |
    | `-o results_update/` | another output directory, to compare with `results/` |
    | `query.fa` | the same query as before |

??? success "RESULT"
    `coli_g0` now holds 6 samples, the 5 initial ones plus `GCA_000005845`.
    `query.fa` comes from `GCA_000780515`, indexed in `coli_g1`, which still
    scores **1.0**.

    The previous version was deleted once the updated one was registered and
    checked. To compare both versions, build with `--keep-previous`: the
    previous `coli_g0` is then left in `coli_build/work/update/previous/coli_g0/`,
    to delete once done.

---

## Step 5 - Check the result

```bash
# Registered indices and the samples they hold
kmhelpers manage -r coli_build/ list
kmhelpers manage -r coli_build/ info --sh coli_g0
kmhelpers manage -r coli_build/ check
```

??? note "Options"
    | Option | Meaning |
    |--------|---------|
    | `-r coli_build/` | the index directory (registry) |
    | `list` | the registered sub-indexes and their sample counts |
    | `info --sh coli_g0` | details of one sub-index: samples, partitions, size |
    | `check` | checks every sub-index on disk against the registry |
