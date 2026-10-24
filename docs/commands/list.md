# list

## Synopsis

Scan a directory or import a sample list, count k-mers, and produce a JSONL sample manifest.

!!! abstract "USAGE"
    ```
    kmhelpers list [OPTIONS] INPUT
    ```

    | Argument | Description |
    |----------|-------------|
    | `INPUT` | Directory to scan, or a plain-text / YAML sample list (required) - see [Input formats](#input-formats) |
    | `-o, --output FILE` | Path for the output JSONL file (required) |
    | `-k, --kmer-size INT` | K-mer size for counting (default: 25) |
    | `--dt, --data-type TEXT` | Data type: `a`/`assembled` (default) or `u`/`unassembled` (raw reads) - see [K-mer counting](#description) |

!!! abstract "I/O"
    **Input:** directory to scan, or a plain-text / YAML sample list  
    **Output:** JSONL sample manifest (`-o`)

## Advanced Options
| Option | Description |
|--------|-------------|
| `--nc, --no-count` | Skip k-mer counting with ntcard |
| `--lg, --leaf-grouping` | Group files by leaf folder; each leaf directory becomes one sample |
| `-p, --paired [REGEX]` | Group mate files (R1/R2) of a directory into one sample, see [Grouping](#description) |
| `-c, --continue` | Resume from an existing output file, skipping already-listed samples |
| `-a, --autorename` | Rename duplicate sample IDs by appending a numeric suffix instead of skipping |
| `--ntt, --ntcard-threads INT` | Number of threads for ntcard k-mer counting (default: 8) |

## When to use a sample list

Scanning a directory is the simplest input: every sequence file becomes a sample
named after the file (or one sample per leaf folder with `--leaf-grouping`, or
one per read pair with `--paired`), and k-mers are counted with ntcard. A sample
list replaces this automatic listing when you need control over it:

- **Precomputed k-mer counts** - give `kmer_count` and ntcard is skipped for that
  sample, which saves hours on large collections already counted elsewhere.
- **Custom sample names** - use your own IDs (accessions, patient IDs) instead of
  names derived from file names.
- **Explicit multi-file samples** - pairs, lanes or several assemblies per sample,
  when neither `--paired` nor `--leaf-grouping` matches your layout.
- **Files from several locations** - mix directories, absolute paths or shared
  storage, or select a subset of a directory.
- **Any rule of your own** - generate the list with a script, for example from a
  metadata table.

A YAML list also carries its top-level keys (other than `samples`) into the
output header.

## Input formats

### Plain text (`.txt`)

One sample per line. Lines starting with `#` and empty lines are ignored.

```
# [sample_id] file_1[,file_2,...] [kmer_count]
sample_A  /data/sample_A_1.fa,/data/sample_A_2.fa  1234567
sample_B  /data/sample_B.fa
/data/sample_C.fa
```

- `sample_id` is optional - if omitted, it is derived from the first filename (without extension)
- Multiple files for one sample are comma-separated
- `kmer_count` is optional - if omitted and `--no-count` is not set, it will be computed

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

## Description

`INPUT` can be a directory (scanned recursively for sequence files) or a sample list file (plain text or YAML) - the type is detected automatically. K-mer counts are parsed or computed for each sample and written to the JSONL manifest.

**Grouping** - by default, each file is treated as its own sample. Use `--leaf-grouping` to group files by leaf folder, where each leaf directory becomes one sample whose ID is the folder name. For any other grouping or naming, use a sample list (see [When to use a sample list](#when-to-use-a-sample-list)).

**Paired reads** - use `--paired` to group mate files into one sample. The last match of a regex is removed from each file name (without extension), and files of the same directory with the same result form one sample named after it. The default regex `[._][Rr]?[12](?=[._]|$)` matches mate tokens such as `_R1`, `_R2`, `_1`, `.2`:

- `S1_R1_clean.fastq.gz` + `S1_R2_clean.fastq.gz` -> `S1_clean`
- `SRR123_1.fq.gz` + `SRR123_2.fq.gz` -> `SRR123`

Files without a mate token stay single-file samples. Pass a custom regex as `--paired=REGEX` (the `=` is required when another argument follows). Without `--paired`, a warning is logged when unassembled files (`--dt u`) look like read pairs. `--paired` cannot be combined with `--leaf-grouping`.

**K-mer counting** - enabled by default. Counting is skipped for any sample that already has a `kmer_count` value. Use `--no-count` to skip counting entirely. The `--data-type` option controls what is counted:

- `assembled` (default) - counts all distinct k-mers; suited for assemblies where every k-mer is expected at least once
- `unassembled` - counts only k-mers appearing at least twice, filtering out likely sequencing errors; suited for raw reads

The same ntcard run also records `kmer_total`, the k-mer occurrences of the sample, which sizes the build memory (see [compose - Partitioning](compose.md#description)).

**Resuming** - if the output file already exists, it is backed up. Pass `--continue` to resume from that backup without reprocessing already-listed samples; otherwise the run starts fresh. Use `--autorename` to rename duplicate sample IDs instead of skipping them.


Top-level keys other than `samples` are written as-is into the output header.

## Output Format

The output is a JSONL file. The first line is a header and the remaining lines are one sample per line:

```jsonl
{"k": 25, "assembled": true}
{"name": "sample_A", "files": ["/data/sequences/sample_A/reads_1.fa", "/data/sequences/sample_A/reads_2.fa"], "kmer_count": 1234567, "kmer_total": 1302114}
{"name": "sample_B", "files": ["/data/sequences/sample_B/reads.fa"], "kmer_count": 987654, "kmer_total": 1011540}
```

This file is the input for [`profile`](profile.md) and [`compose`](compose.md).

## Examples

```bash
# Basic scan, one file per sample
kmhelpers list /data/sequences -o samples.jsonl

# Group files by leaf folder
kmhelpers list /data/sequences -o samples.jsonl --leaf-grouping

# Group paired-end reads (R1/R2) into one sample per pair
kmhelpers list /data/reads -o samples.jsonl --dt u --paired

# Custom mate pattern, e.g. "sample.fwd.fq" / "sample.rev.fq"
kmhelpers list /data/reads -o samples.jsonl --dt u --paired='\.(fwd|rev)$'

# Custom k-mer size
kmhelpers list /data/sequences -o samples.jsonl -k 31

# Skip k-mer counting
kmhelpers list /data/sequences -o samples.jsonl --no-count

# Import from a plain-text file list
kmhelpers list my_files.txt -o samples.jsonl

# Import from a YAML sample list
kmhelpers list my_files.yaml -o samples.jsonl

# Resume an interrupted run without reprocessing already-listed samples
kmhelpers list /data/sequences -o samples.jsonl -c

# Rename duplicate sample IDs instead of skipping them
kmhelpers list /data/sequences -o samples.jsonl -a
```

## Dependencies

K-mer counting relies on [**ntcard**](https://github.com/BirolLab/ntCard), which is automatically installed as a dependency when installing kmhelpers via conda.

> Hamid Mohamadi, Hamza Khan, and Inanc Birol. *ntCard: a streaming algorithm for cardinality estimation in genomics data.* Bioinformatics (2017) 33 (9): 1324–1330. [10.1093/bioinformatics/btw832](https://doi.org/10.1093/bioinformatics/btw832)

## See Also

- [`profile`](profile.md) - produce the profiles YAML file
- [`compose`](compose.md) - use the JSONL output to compose index definitions