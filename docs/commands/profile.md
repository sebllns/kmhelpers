# profile

Analyse a sample YAML file and output a Bloom-filter span profile.

## Usage

```
kmhelpers profile [OPTIONS]
```

## Description

Reads k-mer counts from a YAML file produced by [`list`](list.md), assigns each sample to a Bloom-filter span using the given false-positive rate, and writes a CSV summary and a distribution plot to the output directory.

## Output Files

| File | Description |
|------|-------------|
| `span_distribution.csv` | Span ID, Bloom filter size, and sample count |
| `span_distribution_analysis.png` | Span combination analysis plots |

## Examples

```bash
# Profile with default false-positive rate
kmhelpers profile -i samples.yaml -o ./profile_output

# Use a stricter false-positive rate
kmhelpers profile -i samples.yaml -o ./profile_output -p 0.01

# Export span distribution as JSON
kmhelpers profile -i samples.yaml -o ./profile_output --export
```

## Options

| Option | Description |
|--------|-------------|
| `-i, --input FILE` | Sample YAML file produced by `list` (required) |
| `-o, --output-dir DIR` | Output directory for results (required) |
| `-p, --false-positive-rate FLOAT` | Target Bloom-filter false-positive rate (default: 0.05) |
| `--export` | Export span distribution as JSON |

## Input Format

Expected YAML format (output of `kmhelpers list`):

```yaml
k: 25
false_positive_rate: 0.25   # optional, overridden by --false-positive-rate
samples:
  sample_name:
    kmer_count: 1234567
```