# design

## Synopsis

Scan a directory or import a sample list, then run the full [`list`](list.md) → [`profile`](profile.md) → [`compose`](compose.md) pipeline in a single command.

!!! abstract "USAGE"
    ```
    kmhelpers design -o OUTPUT_DIR -n NAME [OPTIONS] INPUT
    ```

    | Argument | Description |
    |----------|-------------|
    | `INPUT` | Directory to scan, a plain-text / YAML sample list, or an existing JSONL sample index (required) |
    | `-o, --output-dir DIR` | Output directory (required) |
    | `-n, --name TEXT` | Name of the created index (required) |
    | `-S, --session-id TEXT` | Session tag appended to index names (default: current timestamp) |
    | `-k, --kmer-size INT` | K-mer size for counting (default: 25) |
    | `-dt, --data-type TEXT` | Data type: `a`/`assembled` (default) or `u`/`unassembled` (raw reads) |

!!! abstract "I/O"
    **Input:** directory to scan, a plain-text / YAML sample list, or a JSONL sample index (`.jsonl`, in which case the `list` step is skipped and INPUT is used as-is)  
    **Output:**  

    - `OUTPUT_DIR/list/NAME_samples_TIMESTAMP.jsonl` — sample manifest
    - `OUTPUT_DIR/profile/profile.yaml`, `groups.png` — span profile
    - `OUTPUT_DIR/compose/` — index definition files

## Advanced Options

| Option | Description |
|--------|-------------|
| `-g, --group N` | Partition Bloom Filters into `N` storage-balanced groups and overlay on plot (default: 20) |
| `-b, --base FLOAT` | Base for span bucket boundaries (default: 1.1) |
| `-fp, --false-positive-rate FLOAT` | Target Bloom-filter false-positive rate (default: 0.25) |
| `-p, --partition-count INT` | Desired number of partitions per index, 0 for automatic (default: 0) |
| `-nc, --no-count` | Skip k-mer counting with ntcard |
| `-lg, --leaf-grouping` | Group files by leaf folder; each leaf directory becomes one sample |
| `-r, --autorename` | Rename duplicate sample IDs by appending a numeric suffix instead of skipping |
| `-ntt, --ntcard-threads INT` | Number of threads for ntcard k-mer counting (default: 8) |

## Output Structure

```
OUTPUT_DIR/
├── list/
│   └── NAME_samples_TIMESTAMP.jsonl   ← sample manifest (omitted if INPUT is already a JSONL index)
├── profile/
│   ├── profile.yaml                   ← span profile (input for compose)
│   ├── baseline.csv                   ← natural distribution
│   └── groups.png                     ← distribution plot
└── compose/
    └── NAME_layout.yaml               ← index definition files
```

## Description

`design` chains [`list`](list.md), [`profile`](profile.md), and [`compose`](compose.md) into a single invocation. It is equivalent to running the three commands in sequence with the intermediate files automatically routed between steps.

**Step 1 — list:** scans `INPUT` recursively for sequence files (or imports a sample list), counts k-mers with ntcard, and writes a JSONL manifest to `OUTPUT_DIR/list/`. This step is **skipped** if `INPUT` is already a JSONL sample index (`.jsonl`); it is used directly as the manifest for the remaining steps.

**Step 2 — profile:** reads k-mer counts from the manifest, assigns each sample to a Bloom-filter span, computes a storage-balanced grouping, and writes `profile.yaml`, `baseline.csv`, and `groups.png` to `OUTPUT_DIR/profile/`. This step is **skipped automatically** if a layout file already exists at `OUTPUT_DIR/compose/NAME_layout.yaml` (re-run scenario).

**Step 3 — compose:** reads the manifest and the profile to generate index definition files in `OUTPUT_DIR/compose/`.

**Updates** — if the compose layout file already exists from a previous run, the profile step is skipped and the existing layout is used directly. This allows re-running `design` to add new samples to an existing index without re-profiling.

**False-positive rate** — a higher rate reduces Bloom-filter size and disk footprint. At query time the [findere](https://doi.org/10.1007/978-3-030-86692-1_13) algorithm compensates by querying $(k+z)$-mers, reducing the effective FP rate to $p^z$. Recommended: build with `--fp 0.25` (default), query with `-z 6`, giving $0.25^6 \approx 0.024\,\%$ effective FP rate.

## Examples

```bash
# Full pipeline from a directory
kmhelpers design /data/sequences -o ./run -n my_index

# Skip k-mer counting (if counts are already in the sample list)
kmhelpers design /data/sequences -o ./run -n my_index --no-count

# Group files by leaf folder
kmhelpers design /data/sequences -o ./run -n my_index --leaf-grouping

# Custom k-mer size and false-positive rate
kmhelpers design /data/sequences -o ./run -n my_index -k 31 -fp 0.1

# Tag the session
kmhelpers design /data/sequences -o ./run -n my_index -S v2

# Force a specific partition count
kmhelpers design /data/sequences -o ./run -n my_index -p 4

# Import from a plain-text file list
kmhelpers design my_files.txt -o ./run -n my_index

# Re-use an existing JSONL sample index, skipping the list step
kmhelpers design ./run/list/my_index_samples_20260101_120000.jsonl -o ./run -n my_index
```

## See Also

- [`list`](list.md) — list step only
- [`profile`](profile.md) — profile step only
- [`compose`](compose.md) — compose step only
- [`build`](build.md) — validate and build indices from the generated definition files
