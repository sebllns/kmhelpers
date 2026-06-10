# profile

Analyse a sample YAML file and produce a Bloom-filter span profile.

## Usage

```
kmhelpers profile [OPTIONS]
```

## Description

A *span* is an integer `s = floor(log2(n))`, where `n` is the number of distinct
$k$-mers in a sample. It identifies the Bloom-filter size class required to index
that sample at the target false-positive rate: all samples in span `s` have between
`2^s` and `2^(s+1)-1` distinct $k$-mers and are stored in a Bloom filter of the
same size.

A *span profile* is the distribution of samples across spans, together with
candidate groupings of those spans into sub-indices and a recommended grouping that
minimises the number of sub-indices while balancing storage cost. Fewer spans means
fewer index files opened at query time, which can significantly improve query
performance on I/O-bound storage.

`profile` reads $k$-mer counts from a YAML file produced by [`list`](list.md),
assigns each sample to its span, and writes a CSV summary, a distribution plot,
and a YAML profile to the output directory.

## Output Files

| File | Description |
|------|-------------|
| `span_distribution.csv` | Span ID, Bloom filter size, and sample count |
| `span_distribution_analysis.png` | Span combination analysis plots |
| `profile.yaml` | Summary: $k$, false-positive rate, sample count, biggest sample, max $k$-mer count, and the recommended profile with all alternatives |

## Options

| Option | Description |
|--------|-------------|
| `-i, --input FILE` | Sample YAML file produced by `list` (required) |
| `-o, --output-dir DIR` | Output directory for results (required) |
| `--false-positive-rate, --fp FLOAT` | Target Bloom-filter false-positive rate (default: 0.25) |
| `-g, --group N` | Partition spans into `N` storage-balanced groups and overlay the result on the plot (default: 0 = auto) |

## Examples

```bash
# Profile with default false-positive rate
kmhelpers profile -i samples.yaml -o ./profile_output

# Use a stricter false-positive rate
kmhelpers profile -i samples.yaml -o ./profile_output --fp 0.05

# Force a specific number of span groups
kmhelpers profile -i samples.yaml -o ./profile_output -g 3
```

## Input Format

Expected YAML format (output of `kmhelpers list`):

```yaml
k: 25
false_positive_rate: 0.25   # optional, overridden by --false-positive-rate
samples:
  sample_name:
    kmer_count: 1234567
```