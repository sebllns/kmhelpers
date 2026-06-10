# apply

Build k-mer indices from index definition files.

## Usage

```
kmhelpers apply [OPTIONS] INPUT_FILES...
```

## Description

`apply` is the primary build command. It reads one or more index definition files (`.json`/`.yaml`) and builds the declared indices, registering them on completion.

- If the input is a **span registry**, sub-index definition files are resolved from the same directory and merged into the named indices after building.
- **Parent indices** are built automatically when required.
- Filtering by `--name` or `--span` restricts which indices are processed.
- Options can be loaded from a config file with `-c`; command-line flags take precedence.

## Examples

```bash
# Build all indices in a definition file
kmhelpers apply index.yaml -w /output

# Build only selected indices by name (comma-separated or repeated flags)
kmhelpers apply index.yaml -w /output -n idx1,idx2
kmhelpers apply index.yaml -w /output -n idx1 -n idx2

# Build only specific spans
kmhelpers apply index.yaml -w /output -s 28
kmhelpers apply index.yaml -w /output -s 27,28,29
kmhelpers apply index.yaml -w /output -s 27-30

# Reuse parameters from an existing parent index
kmhelpers apply index.yaml -w /output -n my_index --from parent_index

# Show progress bar during building
kmhelpers apply index.yaml -w /output --show-progress

# Skip compression of intermediate files
kmhelpers apply index.yaml -w /output --skip-compression

# Resolve sample paths from a base directory
kmhelpers apply index.yaml -w /output -b /data/samples

# Set number of threads and minimizer size
kmhelpers apply index.yaml -w /output -t 8 --minim-size 12

# Abort on first error
kmhelpers apply index.yaml -w /output --fail-on-error

# Notify by email when done
kmhelpers apply index.yaml -w /output --notify user@example.com

# Load options from a config file
kmhelpers apply index.yaml -c config.yaml
```

## Options

| Option | Description |
|--------|-------------|
| `INPUT_FILES...` | Index definition file(s) (`.json`/`.yaml`) (required) |
| `-w, --work-dir DIR` | Working directory for output |
| `-c, --config FILE` | Config file (command-line takes precedence) |
| `-b, --base-path DIR` | Base path to resolve relative sample paths |
| `-r, --registry DIR` | Custom base path to kmindex registry |
| `-o, --bloom-dir DIR` | Custom base path to kmindex Bloom filters directory |
| `-s, --span TEXT` | Span(s) to build: single value, comma-separated, or range (e.g. `27-30`) |
| `-n, --name TEXT` | Index ID(s) to build (repeatable or comma-separated) |
| `--from TEXT` | Reuse build parameters from a parent index |
| `--minim-size INT` | Minimizer size (default: 10) |
| `-t, --threads INT` | Number of threads (default: 1) |
| `-p, --partition-count INT` | Override number of partitions |
| `--existing TEXT` | Action for pre-existing index folders: `fail`, `register`, `rename`, `replace`, `register_or_replace`, `register_or_rename` (default: `fail`) |
| `--skip-compression` | Skip compression of intermediate files during build |
| `--show-progress` | Show progress bar with elapsed and estimated remaining time |
| `--fail-on-error` | Abort on first failure instead of continuing |
| `--notify EMAIL` | Send email notification on exit (requires sendmail) |
| `-v, --verbose` | Verbose output |

## See Also

- [`plan`](plan.md) — preview the build plan with path validation
- [`compose`](compose.md) — generate index definition files
- [`pipeline`](pipeline.md) — run multiple steps in sequence
