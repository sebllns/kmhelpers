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

## Examples

```bash
# Build all indices in a definition file
kmhelpers apply index.yaml -w /output

# Build only selected indices by name
kmhelpers apply index.yaml -w /output --name my_index

# Build only specific spans
kmhelpers apply index.yaml -w /output --span 28 --span 31

# Build a span range
kmhelpers apply index.yaml -w /output --span 27-30

# Dry-run: output a bash script without executing
kmhelpers apply index.yaml -w /output --dry-run

# Notify by email when done
kmhelpers apply index.yaml -w /output --notify user@example.com

# Abort on first error
kmhelpers apply index.yaml -w /output --fail-on-error
```

## Options

| Option | Description |
|--------|-------------|
| `INPUT_FILES...` | Index definition file(s) (`.json`/`.yaml`) |
| `-w, --work-dir DIR` | Working directory for output |
| `-c, --config FILE` | Config file (command-line takes precedence) |
| `--span TEXT` | Span(s) to build (single, comma-separated, or range) |
| `-n, --name TEXT` | Index name(s) to build |
| `--dry-run` | Output a ready-to-execute bash script without running |
| `--plan` | Like `--dry-run` but with upfront path validation |
| `--show-progress` | Show progress bar with elapsed/estimated time |
| `--notify EMAIL` | Send email notification on exit (requires sendmail) |
| `--fail-on-error` | Abort on first failure instead of continuing |
| `--skip-compression` | Skip intermediate file compression |
| `--existing POLICY` | How to handle pre-existing index folders: `fail`, `register`, `rename`, `replace` |
| `--from TEXT` | Reuse build parameters from a parent index |

## See Also

- [`plan`](plan.md) — preview the build plan with path validation
- [`compose`](compose.md) — generate index definition files
- [`pipeline`](pipeline.md) — run multiple steps in sequence