# compose

## Synopsis

Compose index definition file(s) from a sample list produced by [`list`](list.md). Building a new index requires a profile from [`profile`](profile.md).

!!! abstract "USAGE"
    ```
    kmhelpers compose -o COMPOSE_DIR -n NAME [-pf PROFILES_FILE] [-S SESSION] [OPTIONS] INPUT_FILE
    ```

    | Argument | Description |
    |----------|-------------|
    | `INPUT_FILE` | JSONL sample list produced by `list` |
    | `-o, --output-dir COMPOSE_DIR` | Output directory for index definitions |
    | `-n, --name TEXT` | Name of created or updated index |
    | `-pf, --profiles-file FILE` | Profiles YAML file with index configuration (required to build a new index) |
    | `-S, --session SESSION` | Session name: subdirectory of `COMPOSE_DIR/NAME/` and tag appended to index names (default: timestamp) |

!!! abstract "I/O"
    **Input:** JSONL sample list (from [`list`](list.md)), profiles YAML required only for new index creation (from [`profile`](profile.md))  
    **Output:** the session in `COMPOSE_DIR/NAME/SESSION/` (`index.yaml`, `samples.jsonl`, `summary.csv`, `shards/`), and the layout `COMPOSE_DIR/NAME/layout.yaml`. Pass `COMPOSE_DIR` (with `-S SESSION`) to `plan`, `build` or `apply`

## Advanced Options

| Option | Description |
|--------|-------------|
| `-pr, --profile TEXT` | Profile name to use (default: `default_profile` from profiles file) |
| `-P, --partition-count INT` | Hidden. Fix the partition count of every shard for the life of the index: inherited by every later session, no longer adapted to the system limits of `plan`/`build`. 0 (default) lets the first `plan` of each shard size it, see Partitioning below |
| `--minim-size INT` | Minimizer size (4-15), fixed for the life of the index (default: 10 for a new index, the layout's value on an update) |
| `-sb, --shard-budget INT` | Shard budget: a shard of span `s` holds at most `ceil8(budget / base^s)` samples (e.g. `2**43`); 0 for no limit (default: `2**43` for a new index, the layout's rule on an update) |
| `--shard-budget-bytes SIZE` | Hidden. Cap a shard by its size on disk (e.g. `256GB`, `500000MB`) rather than by `--shard-budget`: when set, `--shard-budget` is not used. Cannot be combined with `--shard-budget` |
| `-ab, --abundance-bits INT` | Build an abundance index with `N` bits per cell (2^N abundance classes); 0 builds a presence/absence index (default: 0) |

## Description

Takes a JSONL sample list (produced by [`list`](list.md)) and generates index definition
files that can be passed to [`plan`](plan.md), [`build`](build.md) or [`apply`](apply.md).

Output files are written to `COMPOSE_DIR/NAME/SESSION/`, where `SESSION` defaults to the
current timestamp if `--session` is not provided:

- `index.yaml` describes the session: parameters, size, and the shards it adds samples to;
- `shards/<shard>.yaml` lists the samples of each shard, and `samples.jsonl` their files;
- `summary.csv` has one row per shard.

Pass `COMPOSE_DIR` (or `COMPOSE_DIR/NAME`, or the session's `index.yaml`) to `plan`,
`build` or `apply`, with `-S SESSION` to pick a session other than the last one.

**Building a new index** - provide `--profiles-file` (produced by [`profile`](profile.md)).
A layout file is written to `COMPOSE_DIR/NAME/layout.yaml` for future updates.

**Updating an existing index** - omit `--profiles-file`. The layout file at
`COMPOSE_DIR/NAME/layout.yaml` is detected and loaded automatically.

If `--profile` is not specified, the `default_profile` field in the profiles file is used.

**Minimizer size** - set at design (`--minim-size`, default 10) and recorded in the layout and
in the session's definitions. Indexes can only be merged when they share it, so an update takes
the layout's value and refuses another one. `plan`, `apply` and `build` have no `--minim-size`.

**Partitioning** - each Bloom filter is split into N partition files, and a shard can only be
merged with updates built with the same N. By default `compose` leaves it open, and `plan`
(or `apply`/`build`) chooses it for each shard, in this order:

1. a shard already built in `BUILD_DIR` keeps its count, so the session merges into it; any
   other value is ignored, with a warning;
2. a part whose kmtricks runs are already started in `BUILD_DIR/work/SESSION/` keeps theirs
   (`apply` after `plan`, a resumed build);
3. the count fixed at design with `-p`;
4. otherwise, a count sized from the resource limits (`--limits`) for a full shard.

`plan`, `apply` and `build` have no `-p`: they never write the design, and each machine sizes the
shards it builds first. Fixing `-p` at design is inherited by every later session and is no longer
adapted to the system limits.

!!! warning "Deep raw reads"
    The automatic sizing estimates memory from the distinct k-mers kept in the Bloom filters.
    kmtricks counts every k-mer *occurrence* of a sample, so for deep raw reads (e.g.
    metabarcoding) it needs far more: fix `-p` at design, sized from the occurrences (about
    `occurrences / p × 8 bytes` per thread).

The layout also records, per span, the samples composed so far (`total_samples`) and the number
of sessions that added samples to it (`updates`).

**Sharding** - a span is split into independent shards, instead of one index growing without
bound. Shards are never merged together: each one is built and registered on its own, and a
query hits them all.

The per-span sample limit of a shard follows one rule:

- the shard budget (from Logan), on by default: a shard of span `s` holds at most
  `ceil8(budget / base^s)` samples (`--shard-budget`, default `2**43`, about k-mers x samples).
  `--shard-budget 0` disables it;
- or, with the hidden `--shard-budget-bytes SIZE`, its size on disk instead: a shard costs about
  `bf_size x samples x bitw / 8` bytes, rounded down to a multiple of 8 samples (minimum 8).

The rule (`shard_budget` or `shard_size`) and the shard limit of each span (`max_samples`) are
written to the layout file, together with the shards and their sample counts, so a later
session knows where to continue. An update keeps the layout's rule; passing `--shard-budget` or
`--shard-budget-bytes` again re-shards it, affecting only the shards opened later. Layouts
written with the former chunk model read as a shard budget of `chunk_budget x shard_chunks`.

How a shard is split into kmtricks chunks is decided at build time, see
[build - Shards and chunks](build.md#shards-and-chunks).

An update fills the last shard of the span until that limit is reached, then opens a new one.
Filling a shard means merging the session's new samples into it; only chunks (a build-time
split, see [plan](plan.md)) are merged as well.

Shards are named `NAME_g<i>_p<k>`. Without any limit (`--shard-budget 0`), a span keeps a
single index named `NAME_g<i>`.

**Abundance** - by default an index records the presence or absence of each k-mer in each
sample. With `--abundance-bits N`, each sample gets `N` bits per Bloom filter cell instead of
one, holding the abundance class of the k-mer (2^N classes, kmindex uses 2 by default). The
index is then built by kmtricks with `--mode hash:bfc:bin --bitw N`, takes `N` times more
space, and a query reports the abundance class of each sample instead of the fraction of
k-mers found. `N` is stored in the layout and fixed for the life of the index: an update with
another value is refused.

**Hard min** - k-mers seen fewer times than the `abundance_min` of the JSONL header are
dropped at build time. `list` sets it to 1 for assembled data and 2 for raw reads.


## Examples

```bash
# Build a new index (writes layout to ./db/my_index/layout.yaml)
kmhelpers compose samples.jsonl -o ./db -n my_index -pf profiles.yaml

# Build with a session tag (output goes to ./db/my_index/my_session/)
kmhelpers compose samples.jsonl -o ./db -n my_index -pf profiles.yaml -S my_session

# Use a specific profile
kmhelpers compose samples.jsonl -o ./db -n my_index -pf profiles.yaml --profile baseline

# Fix the partition count of every shard (inherited by later sessions)
kmhelpers compose samples.jsonl -o ./db -n my_index -pf profiles.yaml --partition-count 4

# Split spans into smaller shards
kmhelpers compose samples.jsonl -o ./db -n my_index -pf profiles.yaml --shard-budget 2**40

# Update an existing index (auto-detects ./db/my_index/layout.yaml)
kmhelpers compose samples.jsonl -o ./db -n my_index
```

## See Also

- [`list`](list.md) - produce the JSONL sample list
- [`profile`](profile.md) - produce the profiles YAML file
- [`apply`](apply.md) - build indices from the generated definition files
