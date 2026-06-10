# list

Recursively scan a directory and produce a JSONL sample manifest with optional k-mer counting.

## Usage

```
kmhelpers list [OPTIONS] OUTPUT_FILE
```

## Description

Scans a directory recursively for sequence files and writes a JSONL sample manifest. By default, each file is treated as its own sample. Use `--leaf-grouping` to group files by leaf folder, where each leaf directory becomes one sample whose ID is the folder name.

K-mer counting is enabled by default. If the output file already exists and is incomplete, the run resumes from where it left off without recounting already-finished samples. Use `--no-count` to skip counting entirely.

## Examples

```bash
# Basic scan, one file per sample
kmhelpers list samples.jsonl -i /data/sequences

# Group files by leaf folder
kmhelpers list samples.jsonl -i /data/sequences --leaf-grouping

# Custom k-mer size
kmhelpers list samples.jsonl -i /data/sequences -k 31

# Skip k-mer counting
kmhelpers list samples.jsonl -i /data/sequences --no-count

# Import from a plain text file list instead of scanning a directory
kmhelpers list samples.jsonl -l my_files.txt

# Rename duplicate sample IDs instead of skipping them
kmhelpers list samples.jsonl -i /data/sequences -r
```

## Options

| Option | Description |
|--------|-------------|
| `OUTPUT_FILE` | Path for the output JSONL file (required) |
| `-i, --input DIR` | Input directory to scan recursively |
| `-l, --list FILE` | Import input list in plain text format |
| `-k, --kmer-size INT` | K-mer size for counting (default: 25) |
| `-t, --data-type TEXT` | Data type: `a`/`assembled` (default) or `u`/`unassembled` (raw reads) |
| `--no-count` | Skip k-mer counting with ntcard |
| `--leaf-grouping` | Group files by leaf folder; each leaf directory becomes one sample |
| `-r, --autorename` | Rename duplicate sample IDs by appending a numeric suffix instead of skipping |
| `--ntcard-threads, --ntt INT` | Number of threads for ntcard k-mer counting (default: 8) |

## Output Format

The output is a JSONL file. The first line is a header and the remaining lines are one sample per line:

```jsonl
{"k": 25, "assembled": true}
{"name": "sample_A", "files": ["/data/sequences/sample_A/reads_1.fa", "/data/sequences/sample_A/reads_2.fa"], "kmer_count": 1234567}
{"name": "sample_B", "files": ["/data/sequences/sample_B/reads.fa"], "kmer_count": 987654}
```

This file is the input for [`profile`](profile.md) and [`compose`](compose.md).
