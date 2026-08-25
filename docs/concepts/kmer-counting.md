# K-mer Counting

## What is a k-mer

A k-mer is a substring of length `k` extracted from a sequence. K-mer counting reduces
a sequence file to a single number: how many solid k-mers it contains.

## Why kmhelpers counts solid k-mers

Each sample's k-mer count drives its Bloom-filter size: more k-mers need a larger
filter to hold a target false-positive rate. [`list`](../commands/list.md) counts
k-mers per sample into the JSONL manifest; [`profile`](../commands/profile.md) uses
those counts to assign each sample a size class (span) and group samples into
storage-balanced sub-indices.

## Counting modes

kmhelpers wraps [ntCard](https://github.com/BirolLab/ntCard), a streaming cardinality
estimator, to avoid loading full k-mer sets in memory. ntCard reports two base
statistics per file:

- **F0**, number of distinct k-mers
- **F1**, total k-mer occurrences, counted with multiplicity

!!! note "Solid k-mer"
    A k-mer is **solid** if it occurs at least twice in the dataset; singletons
    are likely sequencing errors. Assemblies are already curated, so
    every distinct k-mer is already solid: DISTINCT and SOLID coincide.

From these, `KmerCounter` (`pykmhelpers/core/kmer.py`) derives three modes:

| Mode | Value | Use case |
|------|-------|----------|
| `DISTINCT` | F0 | Assembled sequences, where every k-mer is expected to appear at least once |
| `SOLID` | F0 - freq[1] | Raw reads, where k-mers occurring exactly once (`freq[1]`) are likely sequencing errors |
| `TOTAL` | F1 | Total k-mer occurrences across all reads |

The `list` and `design` commands expose this choice through `-dt, --data-type`:
`assembled` maps to `DISTINCT`, `unassembled` maps to `SOLID`.

**Assembled sequences** have already been through the assembler's own error
correction and consensus step, so nearly every k-mer they contain is genuine.
There is no singleton noise to filter, DISTINCT and SOLID coincide, so counting
simply uses `DISTINCT` (F0).

**Raw reads** still carry uncorrected sequencing errors. A true k-mer is expected
to recur across the reads that overlap its genome position, while an error
almost always produces a k-mer seen only once. `SOLID` counting (F0 - freq[1])
drops those singletons, keeping only the recurring, solid k-mers as a cleaner
estimate of the sample's real k-mer content.
