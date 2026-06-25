# compose

Compose index definition file(s) from a sample list produced by [`list`](list.md). Building a new index requires a profile from [`profile`](profile.md).

!!! abstract "USAGE"
    ```
    kmhelpers compose -o OUTPUT_DIR -n NAME [-pf PROFILES_FILE] [-S SESSION_NAME] [OPTIONS] INPUT_FILE
    ```

    | Argument | Description |
    |----------|-------------|
    | `INPUT_FILE` | JSONL sample list produced by `list` |
    | `-o, --output-dir DIR` | Output directory for index definitions |
    | `-n, --name TEXT` | Name of created or updated index |
    | `-pf, --profiles-file FILE` | Profiles YAML file with index configuration (required to build a new index) |
    | `-S, --session-id TEXT` | Session tag appended to index names (default: timestamp) |


## Advanced Options

| Option | Description |
|--------|-------------|
| `-pr, --profile TEXT` | Profile name to use (default: `default_profile` from profiles file) |
| `-p, --partition-count INT` | Desired number of partitions per index, 0 for automatic (default: 0) |
| `-b, --split-size SIZE` | Max run size (e.g. `10GB`, `5000MB`) before splitting samples across indices |
| `-m, --partition-min-size SIZE` | Minimum partition file size (e.g. `500MB`, `1GB`) |
| `-P, --partition-count-limit INT` | Upper bound on auto partition count (default: 256) |

## Description

Takes a JSONL sample list (produced by [`list`](list.md)) and generates index definition
files that can be passed to [`apply`](apply.md).

Output files are written to `OUTPUT_DIR/NAME/SESSION/`, where `SESSION` defaults to the
current timestamp if `--session-id` is not provided.

**Building a new index** — provide `--profiles-file` (produced by [`profile`](profile.md)).
A layout file is written to `OUTPUT_DIR/NAME_layout.yaml` for future updates.

**Updating an existing index** — omit `--profiles-file`. The layout file at
`OUTPUT_DIR/NAME_layout.yaml` is detected and loaded automatically.

If `--profile` is not specified, the `default_profile` field in the profiles file is used.

**Partitioning** — each Bloom filter is split into N partition files. The partition count is
determined automatically by default, or set explicitly with `--partition-count`. Use
`--partition-min-size` to enforce a minimum file size per partition, or
`--partition-count-limit` to cap the auto-computed count.

**Splitting** — when the accumulated size of samples assigned to a span exceeds `--split-size`,
they are distributed across multiple sub-indices rather than one. This is useful to keep
individual index files manageable for large datasets.


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

- [`list`](list.md) — produce the JSONL sample list
- [`profile`](profile.md) — produce the profiles YAML file
- [`apply`](apply.md) — build indices from the generated definition files
