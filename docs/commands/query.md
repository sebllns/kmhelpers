# query

Query indices with FASTA/FASTQ sequences.

## Usage

```
kmhelpers query [OPTIONS] QUERY_FILES...
```

## Description

Searches one or more kmindex indices for sequences from FASTA/FASTQ files. Directories are scanned recursively. Pass `-` to read from stdin.

## Examples

```bash
# Single query file against one index
kmhelpers query -r ./registry -n idx1 -o results query.fa

# Multiple query files with threading
kmhelpers query -r ./registry -n idx1 -t 4 -o results q1.fa q2.fa

# Query multiple indices
kmhelpers query -r ./registry -n idx1 -n idx2 -o results query.fa

# Read from stdin
cat query.fa | kmhelpers query -r ./registry -n idx1 -o results -

# Treat all sequences as one batch query
kmhelpers query -r ./registry -n idx1 --single-query batch1 -o results multi.fa

# Score threshold filtering
kmhelpers query -r ./registry -n idx1 -o results -T 0.1 query.fa

# Output as CSV
kmhelpers query -r ./registry -n idx1 -o results -f csv query.fa
```

## Options

| Option | Description |
|--------|-------------|
| `QUERY_FILES...` | FASTA/FASTQ file(s), directories, or `-` for stdin |
| `-r, --registry-path DIR` | Path to kmindex registry (default: `.`) |
| `-n, --index-ids TEXT` | Index ID(s) to query (default: all) |
| `-o, --output-dir DIR` | Output directory for results (required) |
| `-t, --threads INT` | Number of threads |
| `-T, --threshold FLOAT` | Score threshold for filtering results (default: 0.05) |
| `-b, --batch-query` | Treat all sequences across files as a single query |
| `--single-query NAME` | Name for the batch query |
| `-f, --format TEXT` | Output format: `json`, `yaml`, `md`, `html`, `csv` |
| `-p, --print` | Print results to console in addition to writing files |
| `-P, --timestamp` | Add timestamp suffix to output directory |
| `-e, --existing TEXT` | Conflict resolution: `skip`, `fail`, `delete`, `new-name` |
| `-M, --method TEXT` | Query method: `seq` (parallelise by sequence) or `sub` (by sub-index) |