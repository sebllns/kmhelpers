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
    | `-S, --session-id SESSION` | Session name: subdirectory of `COMPOSE_DIR/NAME/` and tag appended to index names (default: timestamp) |

!!! abstract "I/O"
    **Input:** JSONL sample list (from [`list`](list.md)), profiles YAML required only for new index creation (from [`profile`](profile.md))  
    **Output:** index definition files in `COMPOSE_DIR/NAME/SESSION/`, with `NAME.yaml` as the entry point (`INPUT_FILE` for `plan`, `build` and `apply`)

## Advanced Options

| Option | Description |
|--------|-------------|
| `-pr, --profile TEXT` | Profile name to use (default: `default_profile` from profiles file) |
| `-p, --partition-count INT` | Desired number of partitions per index, 0 for automatic (default: 0) |
| `-si, --shard-size SIZE` | Max size of one shard (e.g. `256GB`, `500000MB`); omit for a single unlimited index per span |
| `-m, --partition-min-size SIZE` | Minimum partition file size (e.g. `500MB`, `1GB`) |
| `-P, --partition-count-limit INT` | Upper bound on auto partition count (default: 256) |

## Description

Takes a JSONL sample list (produced by [`list`](list.md)) and generates index definition
files that can be passed to [`plan`](plan.md), [`build`](build.md) or [`apply`](apply.md).

Output files are written to `COMPOSE_DIR/NAME/SESSION/`, where `SESSION` defaults to the
current timestamp if `--session-id` is not provided. Pass the `NAME.yaml` file in that
directory as the input to `plan`, `build` or `apply` to process the index.

**Building a new index** - provide `--profiles-file` (produced by [`profile`](profile.md)).
A layout file is written to `COMPOSE_DIR/NAME_layout.yaml` for future updates.

**Updating an existing index** - omit `--profiles-file`. The layout file at
`COMPOSE_DIR/NAME_layout.yaml` is detected and loaded automatically.

If `--profile` is not specified, the `default_profile` field in the profiles file is used.

**Partitioning** - each Bloom filter is split into N partition files. The partition count is
determined automatically by default, or set explicitly with `--partition-count`. Use
`--partition-min-size` to enforce a minimum file size per partition, or
`--partition-count-limit` to cap the auto-computed count.

**Sharding** - with `--shard-size`, a span is split into independent shards of at most that
size, instead of one index growing without bound. Shards are never merged together: each one
is built and registered on its own, and a query hits them all.

The per-span sample limit is derived from the Bloom filter size of the span, since a shard
costs about `bf_size x samples / 8` bytes, and is rounded down to a multiple of 8 samples
(minimum 8). It is written to the layout file, together with the shards and their sample
counts, so a later session knows where to continue.

An update fills the last shard of the span until that limit is reached, then opens a new one.
Filling a shard means merging the session's new samples into it; only chunks (a build-time
split, see [plan](plan.md)) are merged as well.

Without `--shard-size`, a span keeps a single index named `NAME_g<i>`. With it, shards are
named `NAME_g<i>_p<k>`.


## Examples

```bash
# Build a new index (writes layout to ./db/my_index_layout.yaml)
kmhelpers compose samples.jsonl -o ./db -n my_index -pf profiles.yaml

# Build with a session tag (output goes to ./db/my_index/my_session/)
kmhelpers compose samples.jsonl -o ./db -n my_index -pf profiles.yaml -S my_session

# Use a specific profile
kmhelpers compose samples.jsonl -o ./db -n my_index -pf profiles.yaml --profile baseline

# Override partition count
kmhelpers compose samples.jsonl -o ./db -n my_index -pf profiles.yaml --partition-count 4

# Set minimum partition size
kmhelpers compose samples.jsonl -o ./db -n my_index -pf profiles.yaml --partition-min-size 500MB

# Split large spans across multiple sub-indices
kmhelpers compose samples.jsonl -o ./db -n my_index -pf profiles.yaml --split-size 10GB

# Update an existing index (auto-detects ./db/my_index_layout.yaml)
kmhelpers compose samples.jsonl -o ./db -n my_index
```

## See Also

- [`list`](list.md) - produce the JSONL sample list
- [`profile`](profile.md) - produce the profiles YAML file
- [`apply`](apply.md) - build indices from the generated definition files
