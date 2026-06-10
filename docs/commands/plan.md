# plan

Preview the build plan from index definition files with upfront path validation.

## Usage

```
kmhelpers plan [OPTIONS] INPUT_FILES...
```

## Description

`plan` is a dry-run mode for [`apply`](apply.md) that validates all paths upfront before outputting a ready-to-execute bash script. Unlike `apply --dry-run`, `plan` aborts early if any path is invalid rather than generating the script unconditionally.

Use `plan` to catch configuration errors before committing to a long build.

## Examples

```bash
# Preview build plan for a definition file
kmhelpers plan index.yaml -w /output

# Preview with specific spans
kmhelpers plan index.yaml -w /output --span 28,31

# Preview for specific index names
kmhelpers plan index.yaml -w /output --name my_index
```

## Options

| Option | Description |
|--------|-------------|
| `INPUT_FILES...` | Index definition file(s) (`.json`/`.yaml`) |
| `-w, --work-dir DIR` | Working directory for index output |
| `-c, --config FILE` | Config file (command-line takes precedence) |
| `--span TEXT` | Span(s) to build: single value, comma-separated, or range (e.g. `27-30`) |
| `-n, --name TEXT` | Index name(s) to build |

## See Also

- [`apply`](apply.md) — actually build the indices
- [`compose`](compose.md) — generate index definition files