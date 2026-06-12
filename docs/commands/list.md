# list

Scan a directory or import a sample list, count k-mers, and produce a JSONL sample manifest.

## Usage

```
kmhelpers list [OPTIONS] INPUT
```

## Description

`INPUT` can be a directory (scanned recursively for sequence files) or a sample list file (plain text or YAML) — the type is detected automatically. K-mer counts are parsed or computed for each sample and written to the JSONL manifest.

By default, each file is treated as its own sample. Use `--leaf-grouping` to group files by leaf folder, where each leaf directory becomes one sample whose ID is the folder name.

K-mer counting is enabled by default. Counting is skipped for any sample that already has a `kmer_count` value (from a resumed run or an imported list). Use `--no-count` to skip counting entirely.

## Options

| Option | Description |
|--------|-------------|
| `INPUT` | Directory to scan, or a plain-text / YAML sample list (required) |
| `-o, --output FILE` | Path for the output JSONL file (required) |
| `-k, --kmer-size INT` | K-mer size for counting (default: 25) |
| `-t, --data-type TEXT` | Data type: `a`/`assembled` (default) or `u`/`unassembled` (raw reads) |
| `--no-count` | Skip k-mer counting with ntcard |
| `--leaf-grouping` | Group files by leaf folder; each leaf directory becomes one sample |
| `-r, --autorename` | Rename duplicate sample IDs by appending a numeric suffix instead of skipping |
| `--ntcard-threads, --ntt INT` | Number of threads for ntcard k-mer counting (default: 8) |

## Input formats for `--list`

### Plain text (`.txt`)

One sample per line. Lines starting with `#` and empty lines are ignored.

```
# [sample_id] file_1[,file_2,...] [kmer_count]
sample_A  /data/sample_A_1.fa,/data/sample_A_2.fa  1234567
sample_B  /data/sample_B.fa
/data/sample_C.fa
```

- `sample_id` is optional — if omitted, it is derived from the first filename (without extension)
- Multiple files for one sample are comma-separated
- `kmer_count` is optional — if omitted and `--no-count` is not set, it will be computed

### YAML (`.yaml` / `.yml`)

```yaml
k: 25
assembled: true
samples:
  sample_A:
    files:
      - /data/sample_A_1.fa
      - /data/sample_A_2.fa
    kmer_count: 1234567
  sample_B:
    files:
      - /data/sample_B.fa
```

Top-level keys other than `samples` are written as-is into the output header.

## Output Format

The output is a JSONL file. The first line is a header and the remaining lines are one sample per line:

```jsonl
{"k": 25, "assembled": true}
{"name": "sample_A", "files": ["/data/sequences/sample_A/reads_1.fa", "/data/sequences/sample_A/reads_2.fa"], "kmer_count": 1234567}
{"name": "sample_B", "files": ["/data/sequences/sample_B/reads.fa"], "kmer_count": 987654}
```

This file is the input for [`profile`](profile.md) and [`compose`](compose.md).

## Examples

```bash
# Basic scan, one file per sample
kmhelpers list /data/sequences -o samples.jsonl

# Group files by leaf folder
kmhelpers list /data/sequences -o samples.jsonl --leaf-grouping

# Custom k-mer size
kmhelpers list /data/sequences -o samples.jsonl -k 31

# Skip k-mer counting
kmhelpers list /data/sequences -o samples.jsonl --no-count

# Import from a plain text file list instead of scanning a directory
kmhelpers list my_files.txt -o samples.jsonl

# Import from a YAML sample list
kmhelpers list my_files.yaml -o samples.jsonl

# Rename duplicate sample IDs instead of skipping them
kmhelpers list /data/sequences -o samples.jsonl -r
```

## Dependencies

K-mer counting relies on [**ntcard**](https://github.com/BirolLab/ntCard), which is automatically installed as a dependency when installing kmhelpers via conda.

> Hamid Mohamadi, Hamza Khan, and Inanc Birol. *ntCard: a streaming algorithm for cardinality estimation in genomics data.* Bioinformatics (2017) 33 (9): 1324–1330. [10.1093/bioinformatics/btw832](https://doi.org/10.1093/bioinformatics/btw832)

## See Also

- [`profile`](profile.md) — produce the profiles YAML file
- [`compose`](compose.md) — use the JSONL output to compose index definitions
