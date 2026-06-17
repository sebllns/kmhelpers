# compose

Compose index definition file(s) from a sample list.

## Usage

```
kmhelpers compose [OPTIONS] INPUT_FILE
```

## Description

Takes a JSONL sample list (produced by [`list`](list.md)) and either a profiles YAML file
(produced by [`profile`](profile.md)) or a layout YAML file (produced by a previous
`compose` run), and generates index definition files that can be passed to [`apply`](apply.md).

Exactly one of `--profiles-file` or `--layout-file` must be provided:

- Use `--profiles-file` to build a new index from a span profile.
- Use `--layout-file` to update an existing index, reusing its span layout.

If `--profile` is not specified, the `default_profile` field in the profiles file is used.

## Examples

```bash
# Basic composition
kmhelpers compose samples.jsonl -o ./db -pf profiles.yaml

# Use a specific profile
kmhelpers compose samples.jsonl -o ./db -pf profiles.yaml --profile baseline

# Override partition count
kmhelpers compose samples.jsonl -o ./db -pf profiles.yaml --partition-count 4

# Set minimum partition size
kmhelpers compose samples.jsonl -o ./db -pf profiles.yaml --partition-min-size 500MB

# Split large spans across multiple sub-indices
kmhelpers compose samples.jsonl -o ./db -pf profiles.yaml --split-size 10GB

# Update an existing index using its layout
kmhelpers compose samples.jsonl -o ./db -ff index_layout.yaml
```

## Options

| Option | Description |
|--------|-------------|
| `INPUT_FILE` | JSONL sample list produced by `list` (required) |
| `-o, --output-dir DIR` | Output directory for index definitions (required) |
| `-pf, --profiles-file FILE` | YAML profiles file defining span lists and BF parameters |
| `-lf, --layout-file FILE` | Fingerprint YAML file from a previous compose run |
| `-pr, --profile TEXT` | Profile name to use (default: `default_profile` from profiles file) |
| `-I, --run-id TEXT` | Session tag appended to index names (default: timestamp) |
| `-n, --name TEXT` | Name of created index database (default: `index`) |
| `-p, --partition-count INT` | Desired number of partitions per index, 0 for automatic (default: 0) |
| `-b, --split-size SIZE` | Max run size (e.g. `10GB`, `5000MB`) before splitting samples across indices |
| `-m, --partition-min-size SIZE` | Minimum partition file size (e.g. `500MB`, `1GB`) |
| `-P, --partition-count-limit INT` | Upper bound on auto partition count (default: 256) |

## See Also

- [`list`](list.md) — produce the JSONL sample list
- [`profile`](profile.md) — produce the profiles YAML file
- [`apply`](apply.md) — build indices from the generated definition files
