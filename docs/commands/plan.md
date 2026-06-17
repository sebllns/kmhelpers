# plan

Preview the build plan from an index definition file and output a ready-to-execute shell script.

## Usage

```
kmhelpers plan [OPTIONS] INPUT_FILE
```

## Description

`plan` validates paths and previews the build commands for an index definition file, then writes a shell script without executing it. It validates all paths upfront and aborts early if any path is invalid.

Use `--offline` to skip local path validation when generating scripts for another machine.

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

## Options

| Option | Description |
|--------|-------------|
| `INPUT_FILE` | Index definition file (`.json`/`.yaml`) (required) |
| `-w, --work-dir DIR` | Working directory for index output (default: `.`) |
| `-b, --base-path DIR` | Base path to resolve relative sample paths |
| `-r, --registry DIR` | Custom base path to kmindex registry |
| `-o, --bloom-dir DIR` | Custom base path to kmindex Bloom filters directory |
| `-s, --span TEXT` | Span(s) to build: single value, comma-separated, or range (e.g. `27-30`) |
| `-n, --name TEXT` | Index ID(s) to build (repeatable or comma-separated) |
| `--from TEXT` | Reuse build parameters from a parent index |
| `--on-conflict TEXT` | Action for pre-existing index folders: `fail`, `register`, `rename`, `replace`, `register_or_replace`, `register_or_rename` (default: `fail`) |
| `-O, --offline` | Skip local path validation (useful when exporting scripts for another machine) |
| `-X, --fail-fast` | Abort on first failure instead of continuing |
| `-v, --verbose` | Verbose output |

## See Also

- [`apply`](apply.md) — actually build the indices
- [`compose`](compose.md) — generate index definition files
