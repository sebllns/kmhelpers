# compose

Compose index definition file(s) from a sample list.

## Usage

```
kmhelpers compose [OPTIONS] INPUT_FILE
```

## Description

Takes a JSONL sample list (produced by [`list`](list.md)) and a profiles YAML file (produced by [`profile`](profile.md)) and generates index definition files that can be passed to [`apply`](apply.md).

The profiles file defines span lists and Bloom filter parameters. If `--profile` is not specified, the `default_profile` field in the profiles file is used.

## Examples

```bash
# Basic composition
kmhelpers compose samples.jsonl -o ./db -f profiles.yaml

# Use a specific profile
kmhelpers compose samples.jsonl -o ./db -f profiles.yaml --profile baseline

# Override partition count
kmhelpers compose samples.jsonl -o ./db -f profiles.yaml --partition-count 4

# Set minimum partition size
kmhelpers compose samples.jsonl -o ./db -f profiles.yaml --partition-min-size 500MB

# Split large spans across multiple sub-indices
kmhelpers compose samples.jsonl -o ./db -f profiles.yaml --split-size 10GB
```

## Options

| Option | Description |
|--------|-------------|
| `INPUT_FILE` | JSONL sample list produced by `list` (required) |
| `-o, --output-dir DIR` | Output directory for index definitions (required) |
| `-f, --profiles-file FILE` | YAML profiles file defining span lists and BF parameters (required) |
| `--profile TEXT` | Profile name to use (default: `default_profile` from profiles file) |
| `--prefix TEXT` | Prefix for index names (default: `span`) |
| `-n, --name TEXT` | Name of created index database (default: `index`) |
| `-p, --partition-count INT` | Desired number of partitions per index, 0 for automatic (default: 0) |
| `-b, --split-size SIZE` | Max run size (e.g. `10GB`, `5000MB`) before splitting samples across indices |
| `-m, --partition-min-size SIZE` | Minimum partition file size (e.g. `500MB`, `1GB`) |
| `-P, --partition-count-limit INT` | Upper bound on auto partition count (default: 256) |

## See Also

- [`list`](list.md) — produce the JSONL sample list
- [`profile`](profile.md) — produce the profiles YAML file
- [`apply`](apply.md) — build indices from the generated definition files
