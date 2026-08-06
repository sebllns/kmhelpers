# kmindex Index

## What is an index

An index is a set of Bloom filters, one per sample, that answer a single question:
does this k-mer appear in this sample? Building an index counts each sample's k-mers
into Bloom filters; querying tests a sequence's k-mers against those filters and
reports, per sample, the fraction found.

## Registry

kmhelpers manages indices through a **registry** directory (`-r, --registry-path`),
rooted at an `index.json` file. It records, per index name, the k-mer size
(`smer_size`), partition count, Bloom filter size, minimizer size, and the list of
registered samples:

```json
{
    "index": {
        "idx_g0": {
            "smer_size": 21,
            "nb_partitions": 4,
            "bloom_size": 10496,
            "nb_samples": 6,
            "samples": ["data_0", "data_1", "..."]
        }
    }
}
```

Each index name at the registry root is a symlink to the physical build directory
currently backing it (e.g. `kmindex_data/upd/idx_g0`). Rebuilding or updating an
index writes a new directory and repoints the symlink; older directories stay on
disk unless removed explicitly.

## On-disk layout

Each physical build directory holds:

| File / folder | Content |
|---|---|
| `kmtricks.fof` | Sample name to input file mapping |
| `options.txt` | Exact kmtricks build parameters (k, min abundance, partitions, format...) |
| `matrices/matrix_N.cmbf` | Bloom-filter matrix for partition `N`, the searchable index data |
| `repartition_gatb/repartition.minimRepart` | Minimizer to partition mapping, reused identically at query time |
| `config_gatb/`, `hash.info` | GATB hashing parameters needed to reproduce k-mer hashes |
| `build_infos.txt` | Build provenance: kmtricks version, host, compiler |

## Partitioning

k-mers are grouped into `nb_partitions` buckets by the minimizer of their sequence
context, not by sample. Each `matrix_N.cmbf` holds the slice of every sample's Bloom
filter that falls into partition `N`. Splitting the index this way bounds memory
during build and lets queries touch only the partitions their k-mers' minimizers
land in.

## Compression

`matrices/*.cmbf` are stored uncompressed by default. [`compress`](../commands/compress.md)
recompresses them in place, optionally reordering sample columns first for a better
ratio. [`query`](../commands/query.md) needs `-c, --compressed` to read a compressed
index.

## Updates

Adding samples to an existing index does not require a full rebuild: kmindex builds
a partial index for the new samples and merges it with the existing one, writing the
merged result to a new physical directory (e.g. `upd` alongside `initial`) and
repointing the registry symlink.

## See also

- [`build`](../commands/build.md), [`plan`](../commands/plan.md), [`apply`](../commands/apply.md), building indices
- [`query`](../commands/query.md), querying indices for k-mer presence
- [`compress`](../commands/compress.md), compressing index matrices
- [K-mer Counting](kmer-counting.md), how sample k-mer counts feed index sizing