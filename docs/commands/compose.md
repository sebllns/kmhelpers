# compose

Compose index definition file(s) from sample lists.

## Usage

```
kmhelpers compose [OPTIONS] INPUT_FILES...
```

## Description

Takes one or more sample YAML files (produced by [`list`](list.md)) and generates index definition files that can be passed to [`apply`](apply.md).

## Examples

```bash
# Basic composition
kmhelpers compose samples.yaml -o ./db -k 31

# With span range
kmhelpers compose samples.yaml -o ./db --min-span 25 --max-span 38

# Split into multiple sub-indices
kmhelpers compose samples.yaml -o ./db --split

# JSON output format
kmhelpers compose samples.yaml -o ./db --format json

# Strict false-positive rate
kmhelpers compose samples.yaml -o ./db -p 0.01

# Partition across 4 sub-indices
kmhelpers compose samples.yaml -o ./db --partition-count 4

# Recount k-mers
kmhelpers compose samples.yaml -o ./db --recount
```

## Options

| Option | Description |
|--------|-------------|
| `INPUT_FILES...` | Sample YAML file(s) produced by `list` |
| `-o, --output-dir DIR` | Output directory for index definitions (required) |
| `-k, --kmer-size INT` | K-mer size |
| `-p, --false-positive-rate FLOAT` | Bloom-filter false-positive rate |
| `--min-span INT` | Minimum span value |
| `--max-span INT` | Maximum span value |
| `--split` | Split samples across multiple sub-indices |
| `--partition-count INT` | Number of partitions for sub-index splitting |
| `--prefix TEXT` | Prefix for index names |
| `-n, --name TEXT` | Override index name |
| `--format TEXT` | Output format: `yaml` (default) or `json` |
| `--recount` | Recount k-mers even if already cached |