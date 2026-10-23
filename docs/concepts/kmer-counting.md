# K-mer counting

## What is a k-mer

A k-mer is a substring of length `k` of a sequence (`-k`, default 25). K-mer counting
reduces a sample to one number: how many different k-mers it holds.

## Why kmhelpers counts k-mers

A sample's k-mer count sets the size of its Bloom filter: more k-mers need a larger filter
to keep the same false-positive rate. [`list`](../commands/list.md) counts the k-mers of
each sample into the sample list; [`profile`](../commands/profile.md) uses these counts to
sort samples into spans and groups (see [How an index is built](building.md)).

## How they are counted

kmhelpers uses [ntCard](https://github.com/BirolLab/ntCard), which estimates the counts
while reading the files once, without holding the k-mers in memory. It gives two numbers
per sample:

- **distinct k-mers**: how many different k-mers;
- **k-mer occurrences**: every k-mer, counted as often as it appears.

!!! note "Solid k-mer"
    A k-mer is **solid** when it appears at least twice. In raw reads, a k-mer seen once
    is most likely a sequencing error; in assemblies, every k-mer is genuine.

The data type (`--dt`, [`list`](../commands/list.md), [`design`](../commands/design.md))
chooses what is counted:

| `--dt` | Counted | Why |
|--------|---------|-----|
| `assembled` (default) | distinct k-mers | assemblies are already corrected: every k-mer is solid |
| `unassembled` (raw reads) | solid k-mers: distinct k-mers minus those seen once | drops the k-mers of sequencing errors, which would inflate the count |

The k-mer occurrences are kept too (`kmer_total` in the sample list): building raw reads
needs memory for every occurrence before the singletons are dropped, so they size the
build (the *k-mer ratio*, see [compose](../commands/compose.md#description)).
