# Choosing groups and partitions

The layout of an index rests on two settings (see the [Glossary](terms.md)):

- **groups** (`-g`, [`design`](../commands/design.md), [`profile`](../commands/profile.md)):
  how many sets of samples of similar sizes. Each group gets the Bloom filter size of its
  largest samples, and is stored as one shard (or several, with a shard budget).
  By default (`-g 0`) the number is chosen: groups are added while each saves at least 20%
  of the storage; with `design`, an index of at most 4 GB keeps one group
  (see [profile - Grouping](../commands/profile.md#description)).
- **partitions** (`-P`, hidden option of `design` and `compose`): how many files the k-mers
  of each shard are spread over. Best left unset: the first [`plan`](../commands/plan.md)
  sizes it from the resources, then it is fixed for the life of the index.

| Goal | Groups (`-g`) | Partitions (`-P`) | Why |
|------|:-------------:|:-----------------:|-----|
| Faster queries | fewer | fewer | each shard is read in turn; fewer files per query |
| Less storage | more | | Bloom filter sizes fit the samples more tightly: a small sample in a group of large ones gets their large filter |
| Lower build RAM | more | more | less held at once by one build; usually handled by `plan` (partitions, threads, chunks) |

Check the storage of each choice of groups in `profile.yaml` and `groups.png` (from
`profile`), and set `-g` explicitly when the automatic choice does not fit your use.
