# apply

## Synopsis

Build k-mer indices from an index definition file.

!!! abstract "USAGE"
    ```
    kmhelpers apply [OPTIONS] INPUT_FILE
    ```

    | Argument | Description |
    |----------|-------------|
    | `INPUT_FILE` | Index definition file `COMPOSE_DIR/NAME/SESSION/NAME.yaml` written by `compose` or `design` (required) |
    | `-o, --output-dir BUILD_DIR` | Index directory: receives the built index, reused across builds and passed to `query -r` (required) |

!!! abstract "I/O"
    **Input:** `COMPOSE_DIR/NAME/SESSION/NAME.yaml` written by `compose`, or `DESIGN_DIR/compose/NAME/SESSION/NAME.yaml` when produced by `design` (see [design - Next Step](design.md#next-step))  
    **Output:** indices in `BUILD_DIR/<name>/`, registered in `BUILD_DIR/index.json`

See [build - Paths](build.md#paths) for the directory layout.

## Advanced Options
| Option | Description |
|--------|-------------|
| `-b, --base-path DIR` | Base path to resolve relative sample paths |
| `-s, --span TEXT` | Span(s) to build: single value, comma-separated, or range (e.g. `27-30`) |
| `-n, --name TEXT` | Index ID(s) to build (repeatable or comma-separated) |
| `--minim-size INT` | Minimizer size (default: 10) |
| `-t, --threads INT` | Number of threads |
| `-p, --partition-count INT` | Partitions per index; ignored when the layout already stores one (see [compose](compose.md)) |
| `--limits JSON` | Resource limits used to auto-size threads/partitions when `--threads` is not set (`ram`, `files`, `threads`), and the inputs of one merge (`ram`, `files`, `maps` = `vm.max_map_count`); see [build - Builds and merges](build.md#builds-and-merges) |
| `--safety-margin FLOAT` | Fraction of a detected system limit to use (default: 0.9) |
| `--max-chunks INT` | Max number of chunks a single index is split into; bigger chunks mean fewer build/merge passes but fewer threads. 0 disables the cap (default: 200) |
| `--keep-previous` | Keep the replaced version of an updated index in `BUILD_DIR/work/SESSION/previous/` instead of deleting it |
| `-NC, --skip-compression` | Skip compression of intermediate files during index building (useful on slow disks) |
| `-SP, --show-progress` | Enable animation that shows the current subindex being built (use in an interactive shell) |
| `-X, --fail-fast` | Abort on first failure instead of continuing |
| `--notify EMAIL` | Send email notification on exit (requires sendmail) |

## Description

`apply` builds the indices declared in `INPUT_FILE` and registers them in `BUILD_DIR/index.json` on completion.

**Parent indices** - built automatically when required.

**Filtering** - use `--name` or `--span` to build only a subset of the declared indices.

## Examples

```bash
# Build all indices in a definition file
kmhelpers apply coli_db/compose/coli/initial/coli.yaml -o coli_build/

# Build only selected indices by name (comma-separated or repeated flags)
kmhelpers apply coli_db/compose/coli/initial/coli.yaml -o coli_build/ -n coli_g0,coli_g1
kmhelpers apply coli_db/compose/coli/initial/coli.yaml -o coli_build/ -n coli_g0 -n coli_g1

# Build only specific spans
kmhelpers apply coli_db/compose/coli/initial/coli.yaml -o coli_build/ -s 28
kmhelpers apply coli_db/compose/coli/initial/coli.yaml -o coli_build/ -s 27-30

# Resolve sample paths from a base directory
kmhelpers apply coli_db/compose/coli/initial/coli.yaml -o coli_build/ -b /data/samples

# Set threads, show progress, abort on first error
kmhelpers apply coli_db/compose/coli/initial/coli.yaml -o coli_build/ -t 8 -SP -X

# Notify by email when done
kmhelpers apply coli_db/compose/coli/initial/coli.yaml -o coli_build/ --notify user@example.com
```

## See Also

- [`plan`](plan.md) - preview the build plan with path validation
- [`build`](build.md) - run plan then apply in a single command
- [`compose`](compose.md) - generate index definition files
- [`pipeline`](pipeline.md) - run multiple steps in sequence
