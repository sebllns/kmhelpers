# query

## Synopsis

Query indices with FASTA/FASTQ sequences.

!!! abstract "USAGE"
    ```
    kmhelpers query [OPTIONS] QUERY_FILES...
    ```

    | Argument | Description |
    |----------|-------------|
    | `QUERY_FILES...` | FASTA/FASTQ file(s), directories, or `-` for stdin (required) |
    | `-r, --registry-path DIR` | Path to kmindex registry (default: `.`) |
    | `-o, --output-dir DIR` | Output directory for results (required) |

!!! abstract "I/O"
    **Input:** FASTA/FASTQ file(s), kmindex registry (`-r`)  
    **Output:** result files in output directory (`-o`)

## Advanced Options
| Option | Description |
|--------|-------------|
| `-n, --index-ids TEXT` | Index ID(s) to query (repeatable, default: all) |
| `-t, --threads INT` | Number of threads (default: 1) |
| `-z, --zvalue INT` | Z-value for findere algorithm to filter false positives (default: 6) |
| `-R, --threshold FLOAT` | Score threshold for filtering results (default: 0.05) |
| `-b, --batch-query` | Treat all sequences across all query files as a single batched query |
| `-s, --single-query NAME` | Name for the single batched query |
| `-a, --aggregate` | Aggregate batch results into one file |
| `-c, --compressed` | Index is compressed (forces `sub` parallelization) |
| `-f, --format TEXT` | Output format: `json` (default), `yaml`, `md`, `html`, `csv` |
| `-p, --print` | Print results to console |
| `-T, --timestamp` | Append timestamp suffix to output directory to avoid overwriting |
| `-e, --existing TEXT` | Conflict resolution: `skip` (default), `fail`, `delete`, `new-name` |
| `-P, --parallel TEXT` | Parallelization strategy: `seq` (by sequence, default) or `sub` (by sub-index) |

## Description

Searches one or more kmindex indices for sequences from FASTA/FASTQ files. Directories are scanned recursively. Pass `-` to read from stdin.

Each value in the output is the fraction of query k-mers found in that sample. Results below `--threshold` are filtered out.

**Batch mode** — use `--batch-query` to treat all sequences across all query files as a single query, or `--single-query NAME` to assign them a specific identifier.

**Parallelization** — `seq` parallelises across sequences (default); `sub` parallelises across sub-indices (forced when `--compressed` is set).

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

# Scan a directory recursively
kmhelpers query -r ./registry -n idx1 -o results ./queries_dir/

# Treat all sequences as one batch query
kmhelpers query -r ./registry -n idx1 --single-query batch1 -o results multi.fa

# Score threshold filtering
kmhelpers query -r ./registry -n idx1 -o results -R 0.1 query.fa

# Output as CSV
kmhelpers query -r ./registry -n idx1 -o results -f csv query.fa
```