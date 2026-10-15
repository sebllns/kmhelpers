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
    **Output:** per query file in the output directory (`-o`): `results.<format>` (TSV by default), `sequence_stats.tsv` and `sample_stats.tsv`, the raw kmindex results in `kmindex_output/`, and optionally a report (`--export`)

## Advanced Options
| Option | Description |
|--------|-------------|
| `-n, --index-ids TEXT` | Index ID(s) to query (repeatable, default: all) |
| `-t, --threads INT` | Number of threads (default: 1) |
| `-z, --zvalue INT` | Z-value for findere algorithm to filter false positives (default: 6) |
| `-R, --threshold FLOAT` | Score threshold for filtering results (default: 0.05) |
| `-b, --batch-query` | Treat all sequences across all query files as a single batched query |
| `-s, --single-query NAME` | Name for the single batched query |
| `-c, --compressed` | Index is compressed (forces `sub` parallelization) |
| `-f, --format TEXT` | Data format: `tsv` (default), `json`, `yaml`, or `none` to keep only the raw kmindex results. `md` and `html` are deprecated, they map to `-f tsv --export <fmt>` |
| `-x, --export TEXT` | Also write a human report: `md` or `html`. Not available with `-f none` |
| `-V, --vec` | Also collect the per-k-mer presence/absence vector, not just the coverage ratio |
| `--page-size INT` | `--export`: sequences per detail page, a single file up to this count, `0` disables paging (default: 100) |
| `--top INT` | `--export`: best samples listed per sequence (default: 100) |
| `--no-stats` | Do not write `sequence_stats.tsv` and `sample_stats.tsv` |
| `-p, --print` | Print the data format to console instead of `results.<format>`, a report is still written to files |
| `-T, --timestamp` | Append timestamp suffix to output directory to avoid overwriting |
| `-e, --existing TEXT` | Conflict resolution: `skip` (default), `fail`, `delete`, `new-name` |
| `-P, --parallel TEXT` | Parallelization strategy: `seq` (by sequence, default) or `sub` (by sub-index) |

## Description

Searches one or more kmindex indices for sequences from FASTA/FASTQ files. Directories are scanned recursively. Pass `-` to read from stdin.

Each value in the output is the fraction of query k-mers found in that sample. Results below `--threshold` are filtered out.

**Batch mode** - use `--batch-query` to treat all sequences across all query files as a single query, or `--single-query NAME` to assign them a specific identifier.

**Parallelization** - `seq` parallelises across sequences (default); `sub` parallelises across sub-indices (forced when `--compressed` is set).

**Statistics** - written unless `--no-stats` (or `--print`). `sequence_stats.tsv` holds
one row per sequence, then a `*` row over all sequences where each sample counts once
with its best score:

| Column | Meaning |
|--------|---------|
| `samples` | samples with a score >= `--threshold` |
| `perfect` | samples with a score of 1 |
| `perfect_pct` | `perfect / samples`, in % |
| `mean`, `median` | over the matching scores |

`sample_stats.tsv` is the reverse view: one row per matched sample (unmatched samples are
left out, an index can hold millions), then a `*` row where each sequence counts once
with its best score over samples:

| Column | Meaning |
|--------|---------|
| `queries` | sequences with a score >= `--threshold` in this sample |
| `perfect` | sequences with a score of 1 |
| `perfect_pct` | `perfect / queries`, in % |
| `mean`, `median` | over the matching scores |

**Data and reports** - `-f` sets the data format: complete, unpaged, meant for scripts.
`--export` adds a human report next to it, so one run gives both. `-f none` writes no
converted file, the raw results stay in `kmindex_output/` (JSON lines).

**md/html reports** (`--export`) - built to stay readable with thousands of sequences and millions of
samples. The main file holds the run information (date, runtime, kmindex version, registry,
threshold, command), the overall statistics, a short guide, and one line per sequence with
its statistics and a link to its details. Each detail section lists the `--top` best
samples of the sequence with their score. Up to `--page-size` sequences, everything is in
`results.md` / `results.html`. Above, the main file is `README.md` / `index.html` and the
details go to `details/page_NNN.<format>`, `--page-size` sequences per page. Statistics
always use every match, `--top` only caps what is listed. All matches stay in
`kmindex_output/`.

```
results/query/
  index.html
  sequence_stats.tsv
  sample_stats.tsv
  details/page_001.html
  details/page_002.html
  kmindex_output/
```

**Presence vector** - by default kmindex reports one coverage ratio `R` per sample:

```json
{"index":"idx_0","query":"q0","samples":{"sample_0":0.69}}
```

With `--vec` it reports the per-k-mer presence vector `P` as well, `R` being its mean:

```json
{"index":"idx_0","query":"q0","samples":{"sample_0":{"P":[1,1,0,...],"R":0.69}}}
```

The score matrix is identical either way. `--vec` adds, per (query, sample), the coverage
stats `n_kmers`, `covered`, `longest_run` (longest stretch of consecutive k-mers found) and
`gaps` (number of missing stretches), which tell a uniformly diluted match apart from one
concentrated on a sub-region:

| Format | Where the vector data goes |
|--------|----------------------------|
| `tsv` | `coverage.tsv` beside `results.tsv`, one row per (query, sample), `P` in a `runs` column |
| `md` | `Coverage` column with a text track (`+` found, `~` partial, `-` missing) in each detail table |
| `html` | `Coverage` column with a colored track showing where the query is covered |
| `json` | stats plus `P` run-length encoded as `[[value, count], ...]` |
| `yaml` | stats plus the same `P` encoding, kept on one line |

In the `P` encoding each pair is a run of consecutive k-mers, `1` present and `0` absent. For
example `[[1, 557], [0, 597], [1, 507]]` means 557 k-mers found, then 597 missing, then 507
found.

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

# TSV data plus an HTML report
kmhelpers query -r ./registry -n idx1 -o results -f tsv --export html query.fa

# Raw kmindex results only
kmhelpers query -r ./registry -n idx1 -o results -f none query.fa

# Paged HTML report for many reads: 500 reads per page, 20 best samples each
kmhelpers query -r ./registry -o results -x html --page-size 500 --top 20 reads.fq.gz

# Per-k-mer coverage track in the HTML report
kmhelpers query -r ./registry -n idx1 -o results -x html --vec query.fa
```