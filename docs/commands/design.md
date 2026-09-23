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
    | `-S, --session-id SESSION` | Session name: subdirectory of `DESIGN_DIR/compose/NAME/` and tag appended to index names (default: timestamp `YYYYMMDD_HHMMSS`) |
    | `-k, --kmer-size INT` | K-mer size for counting (default: 25) |
    | `-dt, --data-type TEXT` | Data type: `a`/`assembled` (default) or `u`/`unassembled` (raw reads) |

!!! abstract "I/O"
    **Input:** directory to scan, a plain-text / YAML sample list, or a JSONL sample index (`.jsonl`, in which case the `list` step is skipped and INPUT is used as-is)  
    **Output (pass to `build`, `plan` or `apply`):** `DESIGN_DIR/compose/NAME/SESSION/NAME.yaml`  
    **Intermediate files (reused by later runs, not passed to `build`):**

    - `DESIGN_DIR/list/NAME_samples_TIMESTAMP.jsonl` - sample manifest
    - `DESIGN_DIR/profile/` - span profile (`profile.yaml`, `baseline.csv`, `groups.png`)
    - `DESIGN_DIR/compose/NAME_layout.yaml` - layout reused by updates

## Output Structure

```
DESIGN_DIR/
├── list/
│   └── NAME_samples_TIMESTAMP.jsonl   intermediate: sample manifest (omitted if INPUT is already a JSONL index)
├── profile/
│   ├── profile.yaml                   intermediate: span profile (input for compose)
│   ├── baseline.csv                   intermediate: natural distribution
│   └── groups.png                     distribution plot
└── compose/                           COMPOSE_DIR
    ├── NAME_layout.yaml               intermediate: layout reused by updates
    └── NAME/
        └── SESSION/
            └── NAME.yaml              -> INPUT_FILE for build/plan/apply
```

## Next Step

Pass the index definition file to [`build`](build.md):

```bash
kmhelpers design /data/sequences -o coli_db -n coli -S initial
kmhelpers build coli_db/compose/coli/initial/coli.yaml -o coli_build
```

Set `-S` to get a predictable path. Without it, `SESSION` is a timestamp: `design` logs the exact `build` command at the end of the run, or look up the folder in `DESIGN_DIR/compose/NAME/`. See [build - Paths](build.md#paths) for the full directory layout.

## Advanced Options

| Option | Description |
|--------|-------------|
| `-g, --group N` | Partition Bloom Filters into `N` storage-balanced groups and overlay on plot (default: 20) |
| `-b, --base FLOAT` | Base for span bucket boundaries (default: 1.1) |
| `-si, --shard-size SIZE` | Max size of one shard (e.g. `10GB`); a span is split into independent shards, see [compose](compose.md) |
| `-fp, --false-positive-rate FLOAT` | Target Bloom-filter false-positive rate (default: 0.25) |
| `-p, --partition-count INT` | Desired number of partitions per index, 0 for automatic (default: 0) |
| `-nc, --no-count` | Skip k-mer counting with ntcard |
| `-lg, --leaf-grouping` | Group files by leaf folder; each leaf directory becomes one sample |
| `-r, --autorename` | Rename duplicate sample IDs by appending a numeric suffix instead of skipping |
| `-ntt, --ntcard-threads INT` | Number of threads for ntcard k-mer counting (default: 8) |

## Description

`design` chains [`list`](list.md), [`profile`](profile.md), and [`compose`](compose.md) into a single invocation. It is equivalent to running the three commands in sequence with the intermediate files automatically routed between steps.

**Step 1 - list:** scans `INPUT` recursively for sequence files (or imports a sample list), counts k-mers with ntcard, and writes a JSONL manifest to `DESIGN_DIR/list/`. This step is **skipped** if `INPUT` is already a JSONL sample index (`.jsonl`); it is used directly as the manifest for the remaining steps.

**Step 2 - profile:** reads k-mer counts from the manifest, assigns each sample to a Bloom-filter span, computes a storage-balanced grouping, and writes `profile.yaml`, `baseline.csv`, and `groups.png` to `DESIGN_DIR/profile/`. This step is **skipped automatically** if a layout file already exists at `DESIGN_DIR/compose/NAME_layout.yaml` (re-run scenario).

**Step 3 - compose:** reads the manifest and the profile to generate the index definition file `DESIGN_DIR/compose/NAME/SESSION/NAME.yaml`.

**Updates** - if the compose layout file already exists from a previous run, the profile step is skipped and the existing layout is used directly. This allows re-running `design` with a new `-S` to add samples to an existing index without re-profiling, then building the new session into the same `BUILD_DIR`.

**False-positive rate** - a higher rate reduces Bloom-filter size and disk footprint. At query time the [findere](https://doi.org/10.1007/978-3-030-86692-1_13) algorithm compensates by querying $(k+z)$-mers, reducing the effective FP rate to $p^z$. Recommended: build with `--fp 0.25` (default), query with `-z 6`, giving $0.25^6 \approx 0.024\,\%$ effective FP rate.

## Examples

```bash
# Full pipeline from a directory, then build
kmhelpers design /data/sequences -o coli_db -n coli -S initial
kmhelpers build coli_db/compose/coli/initial/coli.yaml -o coli_build

# Add new samples to the same index, then build into the same BUILD_DIR
kmhelpers design /data/new_sequences -o coli_db -n coli -S update
kmhelpers build coli_db/compose/coli/update/coli.yaml -o coli_build

# Skip k-mer counting (if counts are already in the sample list)
kmhelpers design /data/sequences -o coli_db -n coli --no-count

# Group files by leaf folder
kmhelpers design /data/sequences -o coli_db -n coli --leaf-grouping

# Custom k-mer size and false-positive rate
kmhelpers design /data/sequences -o coli_db -n coli -k 31 -fp 0.1

# Force a specific partition count
kmhelpers design /data/sequences -o coli_db -n coli -p 4

# Import from a plain-text file list
kmhelpers design my_files.txt -o coli_db -n coli

# Re-use an existing JSONL sample index, skipping the list step
kmhelpers design coli_db/list/coli_samples_20260101_120000.jsonl -o coli_db -n coli
```

## See Also

- [`list`](list.md) - list step only
- [`profile`](profile.md) - profile step only
- [`compose`](compose.md) - compose step only
- [`build`](build.md) - validate and build indices from the generated definition file
