# build

## Synopsis

Validate paths then build k-mer indices from index definition files in a single command.

!!! abstract "USAGE"
    ```
    kmhelpers build [OPTIONS] INPUT_FILE
    ```

    | Argument | Description |
    |----------|-------------|
    | `INPUT_FILE` | Index definition file (`.json`/`.yaml`) from `compose` (required) |
    | `-o, --output-dir DIR` | Working directory for output (required) |

!!! abstract "I/O"
    **Input:** index definition file (`.json`/`.yaml`) from `compose`  
    **Output:** built k-mer index in `OUTPUT_DIR/`, registered in `OUTPUT_DIR/index.json`

## Advanced Options

| Option | Description |
|--------|-------------|
| `-b, --base-path DIR` | Base path to resolve relative sample paths |
| `-s, --span TEXT` | Span(s) to build: single value, comma-separated, or range (e.g. `27-30`) |
| `-n, --name TEXT` | Index ID(s) to build (repeatable or comma-separated) |
| `--minim-size INT` | Minimizer size (default: 10) |
| `-t, --threads INT` | Number of threads (default: 1) |
| `-p, --partition-count INT` | Override number of partitions |
| `-NC, --skip-compression` | Skip compression of intermediate files during build |
| `-SP, --show-progress` | Show progress bar with elapsed and estimated remaining time |
| `-X, --fail-fast` | Abort on first failure instead of continuing |
| `--notify EMAIL` | Send email notification on exit (requires sendmail) |

## Description

`build` chains [`plan`](plan.md) and [`apply`](apply.md) into a single invocation. It is equivalent to running the two commands in sequence.

**Step 1 — plan:** validates all sample paths upfront and writes the equivalent `kmindex` shell script to `OUTPUT_DIR/assets/` and a validation report to `OUTPUT_DIR/logs/`. Fix any path errors before the build starts rather than discovering them mid-run.

**Step 2 — apply:** executes the build and registers all completed indices in `OUTPUT_DIR/index.json`.

**Filtering** — use `--name` or `--span` to build only a subset of the declared indices.

**Notifications** — use `--notify` to receive an email when the build exits (requires `sendmail`). The notification is sent on both success and failure, including on `SIGTERM`.

## Examples

```bash
# Plan then build all indices in a definition file
kmhelpers build index.yaml -o build/

# Filter by name or span
kmhelpers build index.yaml -o build/ -n idx1,idx2
kmhelpers build index.yaml -o build/ -s 28

# Set threads and show progress
kmhelpers build index.yaml -o build/ -t 8 -SP

# Abort on first error
kmhelpers build index.yaml -o build/ -X

# Notify by email when done
kmhelpers build index.yaml -o build/ --notify user@example.com
```

## See Also

- [`plan`](plan.md) — plan step only
- [`apply`](apply.md) — apply step only
- [`design`](design.md) — design the index before building
