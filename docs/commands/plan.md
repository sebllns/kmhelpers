# plan

## Synopsis

Validate paths and preview the build plan from an index definition file, then write a ready-to-execute shell script.

!!! abstract "USAGE"
    ```
    kmhelpers plan [OPTIONS] INPUT_FILE
    ```

    | Argument | Description |
    |----------|-------------|
    | `INPUT_FILE` | Index definition file (`.json`/`.yaml`) from `compose` (required) |
    | `-w, --work-dir DIR` | Working directory for output (default: `.`) |

!!! abstract "I/O"
    **Input:** index definition file (`.json`/`.yaml`) from `compose`  
    **Output:** shell script in `WORK_DIR/assets/`, validation report in `WORK_DIR/logs/`

## Advanced Options
| Option | Description |
|--------|-------------|
| `-b, --base-path DIR` | Base path to resolve relative sample paths |
| `-r, --registry DIR` | Custom base path to kmindex registry |
| `-o, --bloom-dir DIR` | Custom base path to kmindex Bloom filters directory |
| `-s, --span TEXT` | Span(s) to preview: single value, comma-separated, or range (e.g. `27-30`) |
| `-n, --name TEXT` | Index ID(s) to preview (repeatable or comma-separated) |
| `--from TEXT` | Reuse build parameters from a parent index |
| `--on-conflict TEXT` | Action for pre-existing index folders: `fail`, `register`, `rename`, `replace`, `register_or_replace`, `register_or_rename` (default: `fail`) |
| `-O, --offline` | Skip local path validation (useful when exporting scripts for another machine) |
| `-X, --fail-fast` | Abort on first failure instead of continuing |

## Description

`plan` validates all sample paths upfront and previews the `kmindex` commands that would be executed by [`apply`](apply.md), without running them. It writes the equivalent shell script to `WORK_DIR/assets/` and a validation report to `WORK_DIR/logs/`.

**Offline mode** — use `--offline` to skip local path validation when generating scripts destined for another machine.

**Filtering** — use `--name` or `--span` to preview only a subset of the declared indices.

## Examples

```bash
# Preview build plan for a definition file
kmhelpers plan index.yaml -w /output

# Preview with specific spans
kmhelpers plan index.yaml -w /output -s 28,31

# Preview for specific index names
kmhelpers plan index.yaml -w /output -n my_index

# Skip path validation (for exporting scripts)
kmhelpers plan index.yaml -w /output --offline

# Abort on first error
kmhelpers plan index.yaml -w /output --fail-fast
```

## See Also

- [`apply`](apply.md) — actually build the indices
- [`compose`](compose.md) — generate index definition files