# design

## Synopsis

Scan a directory or import a sample list, then run the full [`list`](list.md) → [`profile`](profile.md) → [`compose`](compose.md) pipeline in a single command.

!!! abstract "USAGE"
    ```
    kmhelpers design -o DESIGN_DIR -n NAME [-S SESSION] [OPTIONS] INPUT
    ```

    | Argument | Description |
    |----------|-------------|
    | `INPUT` | Directory to scan, a plain-text / YAML sample list, or an existing JSONL sample index (required) |
    | `-o, --output-dir DESIGN_DIR` | Output directory (required) |
    | `-n, --name NAME` | Name of the created index (required) |
    | `-S, --session SESSION` | Session name: subdirectory of `DESIGN_DIR/compose/NAME/` and tag appended to index names (default: timestamp `YYYYMMDD_HHMMSS`) |
    | `-k, --kmer-size INT` | K-mer size for counting (default: 25) |
    | `--dt, --data-type TEXT` | Data type: `a`/`assembled` (default) or `u`/`unassembled` (raw reads) |

!!! abstract "I/O"
    **Input:** directory to scan, a plain-text / YAML sample list, or a JSONL sample index (`.jsonl`, in which case the `list` step is skipped and INPUT is used as-is)  
    **Output (pass to `build`, `plan` or `apply`):** `DESIGN_DIR` itself, with `-S SESSION` (default: the last session); the session is `DESIGN_DIR/compose/NAME/SESSION/index.yaml`  
    **Intermediate files (reused by later runs, not passed to `build`):**

    - `DESIGN_DIR/list/samples_SESSION.jsonl` - sample manifest, read by the session's shards (not copied)
    - `DESIGN_DIR/profile/` - span profile (`profile.yaml`, `baseline.csv`, `groups.png`)
    - `DESIGN_DIR/compose/NAME/layout.yaml` - layout reused by updates

## Output Structure

```
DESIGN_DIR/                            -> INPUT of build/plan/apply (-S SESSION)
├── list/
│   └── samples_SESSION.jsonl          sample manifest, read by the session (omitted if INPUT is already a JSONL index)
├── profile/
│   ├── profile.yaml                   intermediate: span profile (input for compose)
│   ├── baseline.csv                   intermediate: natural distribution
│   └── groups.png                     distribution plot
└── compose/                           COMPOSE_DIR
    └── NAME/                          the index
        ├── layout.yaml                state of the index: groups, shard budget, shards, partitions, bitw, sessions
        └── SESSION/
            ├── index.yaml             the session: parameters, size and shards (readable summary)
            ├── summary.csv            one row per shard
            └── shards/
                └── NAME_g<i>_p<k>.yaml  the samples this session adds to shard NAME_g<i>_p<k>
```

## Next Step

Pass the index definition file to [`build`](build.md):

```bash
kmhelpers design /data/sequences -o coli_db -n coli -S initial
kmhelpers build coli_db -o coli_build
```

Set `-S` to get a predictable path. Without it, `SESSION` is a timestamp: `design` logs the exact `build` command at the end of the run, or look up the folder in `DESIGN_DIR/compose/NAME/`. See [build - Paths](build.md#paths) for the full directory layout.

## Advanced Options

| Option | Description |
|--------|-------------|
| `-g, --group N` | Partition Bloom Filters into `N` storage-balanced groups and overlay on plot; 0 chooses `N` (default: 0), tuned by the `KMHELPERS_AUTO_GROUP_*` environment variables, see [profile - Grouping](profile.md#description) |
| `-b, --base FLOAT` | Base for span bucket boundaries (default: 1.1) |
| `--sb, --shard-budget INT` | Shard budget: a shard of span `s` holds at most `ceil8(budget / base^s)` samples (default: `2**43` for a new index); 0 for no limit, see [compose](compose.md) |
| `--fp, --false-positive-rate FLOAT` | Target Bloom-filter false-positive rate (default: 0.25) |
| `-P, --partition-count INT` | Hidden. Fix the partition count of every shard for the life of the index: inherited by every later session, no longer adapted to the system limits of `plan`/`build`. 0 (default) lets the first `plan` of each shard size it, see [compose - Partitioning](compose.md#description) |
| `--minim-size INT` | Minimizer size (4-15), fixed for the life of the index (default: 10 for a new index, the layout's value on an update) |
| `--ab, --abundance-bits INT` | Build an abundance index with `N` bits per cell (2^N abundance classes); 0 builds a presence/absence index (default: 0), see [compose](compose.md) |
| `--nc, --no-count` | Skip k-mer counting with ntcard |
| `--ncl, --no-copy-list` | With a JSONL INPUT, point the index definition files to it instead of copying it into the compose output folder; the list must then stay in place and unchanged as it is used for building. A list written by `design` is never copied |
| `--shard-budget-bytes SIZE` | Hidden. Cap a shard by its size on disk (e.g. `10GB`) rather than by `--shard-budget`: when set, `--shard-budget` is not used. Cannot be combined with `--shard-budget`, see [compose](compose.md) |
| `--lg, --leaf-grouping` | Group files by leaf folder; each leaf directory becomes one sample |
| `-p, --paired [REGEX]` | Group mate files (R1/R2) of a directory into one sample, see [list](list.md#description) |
| `-a, --autorename` | Rename duplicate sample IDs by appending a numeric suffix instead of skipping |
| `--ntt, --ntcard-threads INT` | Number of threads for ntcard k-mer counting (default: 8) |

## Description

`design` chains [`list`](list.md), [`profile`](profile.md), and [`compose`](compose.md) into a single invocation. It is equivalent to running the three commands in sequence with the intermediate files automatically routed between steps.

**Step 1 - list:** scans `INPUT` recursively for sequence files (or imports a sample list), counts k-mers with ntcard, and writes a JSONL manifest to `DESIGN_DIR/list/`. This step is **skipped** if `INPUT` is already a JSONL sample index (`.jsonl`); it is used directly as the manifest for the remaining steps.

**Step 2 - profile:** reads k-mer counts from the manifest, assigns each sample to a Bloom-filter span, computes a storage-balanced grouping, and writes `profile.yaml`, `baseline.csv`, and `groups.png` to `DESIGN_DIR/profile/`. This step is **skipped automatically** if a layout file already exists at `DESIGN_DIR/compose/NAME/layout.yaml` (re-run scenario).

**Step 3 - compose:** reads the manifest and the profile to generate the index definition file `DESIGN_DIR/compose/NAME/SESSION/index.yaml`.

**Updates** - if the compose layout file already exists from a previous run, the profile step is skipped and the existing layout is used directly. This allows re-running `design` with a new `-S` to add samples to an existing index without re-profiling, then building the new session into the same `BUILD_DIR`. The new session is merged with the existing index at build time, which keeps both versions on disk - see [`build` - Updating an index](build.md#updating-an-index).

**False-positive rate** - a higher rate reduces Bloom-filter size and disk footprint. At query time the [findere](https://doi.org/10.1007/978-3-030-86692-1_13) algorithm compensates by querying $(k+z)$-mers, reducing the effective FP rate to $p^z$. Recommended: build with `--fp 0.25` (default), query with `-z 6`, giving $0.25^6 \approx 0.024\,\%$ effective FP rate.

## Examples

```bash
# Full pipeline from a directory, then build
kmhelpers design /data/sequences -o coli_db -n coli -S initial
kmhelpers build coli_db -o coli_build

# Add new samples to the same index, then build into the same BUILD_DIR
kmhelpers design /data/new_sequences -o coli_db -n coli -S update
kmhelpers build coli_db -S update -o coli_build

# Skip k-mer counting (if counts are already in the sample list)
kmhelpers design /data/sequences -o coli_db -n coli --no-count

# Group files by leaf folder
kmhelpers design /data/sequences -o coli_db -n coli --leaf-grouping

# Custom k-mer size and false-positive rate
kmhelpers design /data/sequences -o coli_db -n coli -k 31 --fp 0.1

# Force a specific partition count
kmhelpers design /data/sequences -o coli_db -n coli -P 4

# Abundance index of paired raw reads (4 abundance classes)
kmhelpers design /data/reads -o reads_db -n reads --dt u --paired --ab 2

# Import from a plain-text file list
kmhelpers design my_files.txt -o coli_db -n coli

# Re-use an existing JSONL sample index, skipping the list step
kmhelpers design coli_db/list/samples_20260101_120000.jsonl -o coli_db -n coli
```

## See Also

- [`list`](list.md) - list step only
- [`profile`](profile.md) - profile step only
- [`compose`](compose.md) - compose step only
- [`build`](build.md) - validate and build indices from the generated definition file
