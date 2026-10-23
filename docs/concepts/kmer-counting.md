# K-mer counting

kmhelpers needs the k-mer count of each sample: it sets the size of the sample's Bloom
filter, and places it in a span and a group (see [How an index is built](building.md)).
[`list`](../commands/list.md) counts them with [ntCard](https://github.com/BirolLab/ntCard).

What is counted depends on the data type (`--dt`, [`list`](../commands/list.md),
[`design`](../commands/design.md)):

| `--dt` | Counted | Why |
|--------|---------|-----|
| `assembled` (default) | distinct k-mers | assemblies are already corrected: every k-mer is genuine |
| `unassembled` (raw reads) | [solid](terms.md#sequences) k-mers: those seen at least twice | a k-mer seen once is most likely a sequencing error |

**Counts from elsewhere** - the counts can come with the samples instead: a sample list
(plain text or YAML) can give each sample its `kmer_count`, and `list` then does not count
it (see [list - Input formats](../commands/list.md#input-formats)). A JSONL sample list with
the counts can also be given directly to `design`, which then skips `list`. Counting
nothing at all: `list --no-count`.

??? abstract "Raw reads: the k-mer ratio"
    The sample list also keeps every k-mer occurrence (`kmer_total`). Building raw reads
    needs memory for all occurrences before the errors are dropped, so their ratio to the
    count sizes the build (see [compose](../commands/compose.md#description)).
