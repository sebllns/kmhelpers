# plan

## Synopsis

Validate paths and preview the build plan from an index definition file, then write a ready-to-execute shell script.

!!! abstract "USAGE"
    ```
    kmhelpers plan [OPTIONS] INPUT_FILE
    ```

    | Argument | Description |
    |----------|-------------|
    | `INPUT_FILE` | `NAME.yaml` written by `compose` in `OUTPUT_DIR/NAME/SESSION/` (required) |
    | `-o, --output-dir DIR` | Working directory for output (required) |

!!! abstract "I/O"
    **Input:** `NAME.yaml` written by `compose` in `OUTPUT_DIR/NAME/SESSION/`  
    **Output:** shell script in `OUTPUT_DIR/assets/`, validation report in `OUTPUT_DIR/logs/`

## Advanced Options

| Option | Description |
|--------|-------------|
| `-b, --base-path DIR` | Base path to resolve relative sample paths |
| `-s, --span TEXT` | Span(s) to preview: single value, comma-separated, or range (e.g. `27-30`) |
| `-n, --name TEXT` | Index ID(s) to preview (repeatable or comma-separated) |
| `--minim-size INT` | Minimizer size (default: 10) |
| `-t, --threads INT` | Number of threads (default: 1) |
| `-p, --partition-count INT` | Override number of partitions |
| `-NC, --skip-compression` | Skip compression of intermediate files |
| `-SP, --show-progress` | Show progress bar during build |
| `-X, --fail-fast` | Abort on first failure instead of continuing |
| `--notify EMAIL` | Send email notification on exit (requires sendmail) |
| `-r, --registry DIR` | Custom base path to kmindex registry |
| `-bl, --bloom-dir DIR` | Custom base path to kmindex Bloom filters directory |
| `--from TEXT` | Reuse build parameters from a parent index |
| `--on-conflict TEXT` | Action for pre-existing index folders: `fail`, `register`, `rename`, `replace`, `register_or_replace`, `register_or_rename` (default: `fail`) |
| `-O, --offline` | Skip local path validation (useful when exporting scripts for another machine) |

## Description

`plan` takes the `NAME.yaml` file written by [`compose`](compose.md) in `OUTPUT_DIR/NAME/SESSION/`. It validates all sample paths upfront and previews the `kmindex` commands that would be executed by [`apply`](apply.md), without running them. It writes the equivalent shell script to `OUTPUT_DIR/assets/` and a validation report to `OUTPUT_DIR/logs/`.

**Offline mode** — use `--offline` to skip local path validation when generating scripts destined for another machine.

**Filtering** — use `--name` or `--span` to preview only a subset of the declared indices.

## Examples

```bash
# Preview build plan for a definition file
kmhelpers plan index.yaml -o /output

# Preview with specific spans
kmhelpers plan index.yaml -o /output -s 28,31

# Preview for specific index names
kmhelpers plan index.yaml -o /output -n my_index

# Skip path validation (for exporting scripts)
kmhelpers plan index.yaml -o /output --offline

# Abort on first error
kmhelpers plan index.yaml -o /output --fail-fast
```

## See Also

- [`build`](build.md) — run plan then apply in a single command
- [`apply`](apply.md) — actually build the indices
- [`compose`](compose.md) — generate index definition files
