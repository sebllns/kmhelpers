# kmindex

Low-level wrapper commands for direct interaction with kmindex.

## Usage

```
kmhelpers kmindex COMMAND [ARGS]...
```

## Description

`kmindex` provides thin wrappers around the underlying `kmindex` binary. For most workflows, prefer the higher-level commands ([`apply`](apply.md), [`query`](query.md), [`compress`](compress.md)) which add registry management, progress reporting, and error handling.

## Subcommands

| Subcommand | Description |
|------------|-------------|
| `build` | Build a k-mer index directly from a FOF file |
| `query` | Query indices with FASTA/FASTQ sequences |

---

## kmindex build

```
kmhelpers kmindex build [OPTIONS]
```

### Options

| Option | Description |
|--------|-------------|
| `--fof FILE` | File-of-Files listing input samples (required) |
| `-r, --output-registry DIR` | Output kmindex registry path (required) |
| `--output-index-dir DIR` | Directory for index data (default: `.subindexes`) |
| `-k, --kmer-size INT` | K-mer size (default: 25) |
| `-m, --minim-size INT` | Minimizer size (default: 10) |
| `--bloom-size INT` | Bloom filter size for presence/absence (mutually exclusive with `--nb-cell`) |
| `--nb-cell INT` | Number of cells for abundance counting (mutually exclusive with `--bloom-size`) |
| `-t, --threads INT` | Number of threads (default: 1) |
| `-n, --register-as TEXT` | Register index with this ID (auto-generated if not provided) |
| `--compress-intermediate` | Compress intermediate files during build |
| `-v, --verbose` | Verbose output |
| `-y, --yes` | Skip confirmation prompt before building |

### Examples

```bash
# Build presence/absence index
kmhelpers kmindex build --fof samples.fof -r ./registry --bloom-size 10000000

# Build abundance index with custom k-mer size
kmhelpers kmindex build --fof samples.fof -r ./registry --nb-cell 65536 -k 31

# Build with multiple threads and register
kmhelpers kmindex build --fof samples.fof -r ./registry --bloom-size 10000000 -t 8 -n my_index
```

---

## kmindex query

```
kmhelpers kmindex query [OPTIONS]
```

### Options

| Option | Description |
|--------|-------------|
| `-r, --registry-path DIR` | Path to kmindex registry (required) |
| `-n, --index-ids TEXT` | Index ID(s) to query (repeatable, required) |
| `--query-file FILE` | Query file(s) in FASTA/FASTQ format (repeatable, required) |
| `-o, --output-dir DIR` | Output directory for query results (required) |
| `--zvalue INT` | Z-value for findere algorithm (default: 6) |
| `--threshold FLOAT` | Score threshold for filtering results (default: 0.0) |
| `-t, --threads INT` | Number of threads (default: 1) |
| `-s, --single-query TEXT` | Treat all sequences as a single query with this identifier |
| `--aggregate` | Aggregate batch results into one file |
| `--format TEXT` | Output format: `json` (default) or `txt` |
| `-v, --verbose` | Verbose output |

### Examples

```bash
# Single query file against single index
kmhelpers kmindex query -r ./registry -n idx1 --query-file query.fa -o results

# Multiple query files with threading
kmhelpers kmindex query -r ./registry -n idx1 --query-file q1.fa --query-file q2.fa -t 4 -o results

# Multiple indices
kmhelpers kmindex query -r ./registry -n idx1 -n idx2 --query-file query.fa -o results
```
