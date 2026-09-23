# plan

## Synopsis

Validate paths and preview the build plan from an index definition file, then write a ready-to-execute shell script.

!!! abstract "USAGE"
    ```
    kmhelpers plan [OPTIONS] INPUT_FILE
    ```

    | Argument | Description |
    |----------|-------------|
    | `INPUT_FILE` | Index definition file `COMPOSE_DIR/NAME/SESSION/NAME.yaml` written by `compose` or `design` (required) |
    | `-o, --output-dir BUILD_DIR` | Index directory the plan targets, same as for [`build`](build.md) and [`apply`](apply.md) (required) |

!!! abstract "I/O"
    **Input:** `COMPOSE_DIR/NAME/SESSION/NAME.yaml` written by `compose`, or `DESIGN_DIR/compose/NAME/SESSION/NAME.yaml` when produced by `design` (see [design - Next Step](design.md#next-step))  
    **Output:** shell scripts in `BUILD_DIR/assets/`, validation report in `BUILD_DIR/logs/`

See [build - Paths](build.md#paths) for the directory layout.

## Advanced Options

| Option | Description |
|--------|-------------|
| `-b, --base-path DIR` | Base path to resolve relative sample paths |
| `-s, --span TEXT` | Span(s) to preview: single value, comma-separated, or range (e.g. `27-30`) |
| `-n, --name TEXT` | Index ID(s) to preview (repeatable or comma-separated) |
| `--minim-size INT` | Minimizer size (default: 10) |
| `-t, --threads INT` | Number of threads |
| `-p, --partition-count INT` | Partitions per index; ignored when the layout already stores one (see [compose](compose.md)) |
| `-NC, --skip-compression` | Skip compression of intermediate files during index building (useful on slow disks) |
| `--limits JSON` | Resource limits used to auto-size threads/partitions when `--threads` is not set |
| `--safety-margin FLOAT` | Fraction of a detected system limit to use (default: 0.9) |
| `-X, --fail-fast` | Abort on first failure instead of continuing |
| `-r, --registry DIR` | Registry directory (default: `BUILD_DIR`, holds `index.json`) |
| `-bl, --bloom-dir DIR` | Bloom filters directory (default: `BUILD_DIR/kmindex_data`) |
| `--from TEXT` | Reuse build parameters from a parent index |
| `--on-conflict TEXT` | Action for pre-existing index folders: `fail`, `register`, `rename`, `replace`, `register_or_replace`, `register_or_rename` (default: `fail`) |
| `-O, --offline` | Skip local path validation (useful when exporting scripts for another machine) |

## Description

`plan` validates all sample paths of `INPUT_FILE` upfront and previews the `kmindex` commands that would be executed by [`apply`](apply.md), without running them. It writes the equivalent shell scripts to `BUILD_DIR/assets/` (one per sub-index, `<name>_g<span>_<session>.sh`, plus `kmhelpers_apply.sh` running them in order) and a validation report to `BUILD_DIR/logs/`.

**Offline mode** - use `--offline` to skip local path validation when generating scripts destined for another machine.

**Filtering** - use `--name` or `--span` to preview only a subset of the declared indices.

## Examples

```bash
# Preview build plan for a definition file
kmhelpers plan coli_db/compose/coli/initial/coli.yaml -o coli_build/

# Preview with specific spans
kmhelpers plan coli_db/compose/coli/initial/coli.yaml -o coli_build/ -s 28,31

# Preview for specific index names
kmhelpers plan coli_db/compose/coli/initial/coli.yaml -o coli_build/ -n coli_g0

# Skip path validation (for exporting scripts)
kmhelpers plan coli_db/compose/coli/initial/coli.yaml -o coli_build/ --offline

# Abort on first error
kmhelpers plan coli_db/compose/coli/initial/coli.yaml -o coli_build/ -X
```

## See Also

- [`build`](build.md) - run plan then apply in a single command
- [`apply`](apply.md) - actually build the indices
- [`compose`](compose.md) - generate index definition files
