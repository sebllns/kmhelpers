# list

Recursively scan a directory and produce a YAML sample manifest with optional k-mer counting.

## Usage

```
kmhelpers list [OPTIONS] OUTPUT_FILE
```

## Description

Scans a directory recursively and groups files into samples. By default, files are grouped by leaf folder — each leaf directory becomes one sample whose ID is the folder name. Use `--no-grouping` to treat every file independently.

When `--count` is used, each completed k-mer count is saved to a cache file so an interrupted run can resume without recounting already-finished samples. The cache is deleted automatically on successful completion.

## Examples

```bash
# Basic scan, group by leaf folder
kmhelpers list samples.yaml -i /data/sequences

# Include k-mer counting (k=31)
kmhelpers list samples.yaml -i /data/sequences -k 31 --count

# Import from a plain text list instead of scanning a directory
kmhelpers list samples.yaml -l my_files.txt -k 31 --count

# Flat mode: one file = one sample
kmhelpers list samples.yaml -i /data/sequences --no-grouping
```

## Options

| Option | Description |
|--------|-------------|
| `OUTPUT_FILE` | Path for the output YAML file |
| `-i, --input DIR` | Input directory to scan recursively |
| `-l, --list FILE` | Import input list in plain text format |
| `-k, --kmer-size INT` | K-mer size for counting (default: 31) |
| `--count` | Run k-mer counting via ntcard |
| `--no-grouping` | Treat each file as an independent sample |
| `--threads INT` | Number of threads for k-mer counting |

## Output Format

The output YAML contains k-mer counts per sample:

```yaml
k: 31
false_positive_rate: 0.05
samples:
  sample_A:
    kmer_count: 1234567
    files:
      - /data/sequences/sample_A/reads_1.fa
      - /data/sequences/sample_A/reads_2.fa
  sample_B:
    kmer_count: 987654
    files:
      - /data/sequences/sample_B/reads.fa
```

This file is the input for [`profile`](profile.md) and [`compose`](compose.md).