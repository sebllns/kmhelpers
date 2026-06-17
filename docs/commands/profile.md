# profile

Analyse a JSONL sample index and produce a Bloom-filter span profile.

## Usage

```
kmhelpers profile [OPTIONS] LIST_OUTPUT
```

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
plot to the output directory.

## Output Files

| File | Description |
|------|-------------|
| `span_distribution.csv` | Span ID, Bloom filter size, and sample count |
| `profile.yaml` | Natural distribution and storage-balanced grouped profile(s) |
| `span_distribution_analysis.png` | Span combination analysis plots |

## Options

| Option | Description |
|--------|-------------|
| `LIST_OUTPUT` | JSONL sample index produced by `list` (required) |
| `-o, --output-dir DIR` | Output directory for results (required) |
| `--false-positive-rate, -fp FLOAT` | Target Bloom-filter false-positive rate (default: 0.25) |
| `-g, --group N` | Partition spans into `N` storage-balanced groups and overlay on plot (default: 0) |
| `-b, --base FLOAT` | Base for span bucket boundaries (default: 2.0); use values like 1.1 to narrow granularity |

## Examples

```bash
# Profile with default false-positive rate
kmhelpers profile samples.jsonl -o ./profile_output

# Use a stricter false-positive rate
kmhelpers profile samples.jsonl -o ./profile_output -fp 0.05

# Force a specific number of span groups
kmhelpers profile samples.jsonl -o ./profile_output -g 3

# Use a finer bucket granularity
kmhelpers profile samples.jsonl -o ./profile_output --base 1.5
```

## Input Format

Expected JSONL format (output of `kmhelpers list`):

```jsonl
{"k": 25, "assembled": true}
{"name": "sample_name", "files": [...], "kmer_count": 1234567}
```

## See Also

- [`list`](list.md) — produce the JSONL input file
- [`compose`](compose.md) — use the JSONL from `list` and a profile to compose index definitions
