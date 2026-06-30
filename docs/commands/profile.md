# profile

## Synopsis

Analyse a JSONL sample manifest produced by `list` and produce a Bloom-filter span profile.

!!! abstract "USAGE"
    ```
    kmhelpers profile [OPTIONS] LIST_OUTPUT
    ```

    | Argument | Description |
    |----------|-------------|
    | `LIST_OUTPUT` | JSONL sample manifest produced by `list` (required) |
    | `-o, --output DIR` | Output directory for results (required) |
    | `-g, --group N` | Partition Bloom Filters into `N` storage-balanced groups and overlay on plot (default: 0) |
    | `-b, --base FLOAT` | Base for span bucket boundaries (default: 2.0); use values like 1.1 to narrow granularity |

!!! abstract "I/O"
    **Input:** JSONL sample manifest produced by `list`  
    **Output:** `profile.yaml`, `groups.png` in output directory (`-o`)

## Advanced Options

| Option | Description |
|--------|-------------|
| `-fp, --false-positive-rate FLOAT` | Target Bloom-filter false-positive rate (default: 0.25) |

## Output Files

| File | Description |
|------|-------------|
| `profile.yaml` | Natural distribution and storage-balanced grouped profile(s) |
| `groups.png` | Span combination analysis plots |

## Description

A *span* is an integer `s = floor(log_base(n))`, where `n` is the number of distinct
$k$-mers in a sample and `base` controls bucket granularity (default: 2). It identifies
the Bloom-filter size class required to index that sample at the target false-positive
rate.

A *span profile* is the distribution of samples across spans, together with candidate
groupings of those spans into sub-indices. Fewer spans means fewer index files opened
at query time, which improves query performance on I/O-bound storage.

`profile` reads $k$-mer counts from a JSONL file produced by [`list`](list.md), assigns
each sample to its span, and writes a CSV summary, a profile YAML, and a distribution
plot to the output directory. Samples without a `kmer_count` field are skipped.

**False-positive rate** — a higher rate reduces Bloom-filter size and therefore disk
footprint. At query time the [findere](https://doi.org/10.1007/978-3-030-86692-1_13)
algorithm compensates by querying $(k+z)$-mers, reducing the effective FP rate to $p^z$.
Recommended: build with `--fp 0.25` (default), query with `-z 6`, giving
$0.25^6 \approx 0.024\,\%$ effective FP rate.

**Grouping** — use `-g N` to merge spans into `N` storage-balanced sub-indices. Fewer
sub-indices reduce the number of partition files opened per query. The grouping is
overlaid on the distribution plot for visual inspection.

## Examples

```bash
# Profile with default settings
kmhelpers profile samples.jsonl -o ./profile_output

# Use a stricter false-positive rate
kmhelpers profile samples.jsonl -o ./profile_output -fp 0.05

# Force a specific number of span groups
kmhelpers profile samples.jsonl -o ./profile_output -g 3

# Use a finer bucket granularity
kmhelpers profile samples.jsonl -o ./profile_output -b 1.5
```

## See Also

- [`list`](list.md) — produce the JSONL input file
- [`compose`](compose.md) — use the JSONL from `list` and a profile to compose index definitions