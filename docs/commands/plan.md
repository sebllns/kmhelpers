# plan

## Synopsis

Validate paths and preview the build plan from an index definition file, then write a ready-to-execute shell script.

!!! abstract "USAGE"
    ```
    kmhelpers plan [OPTIONS] INPUT
    ```

    | Argument | Description |
    |----------|-------------|
    | `INPUT` | The design directory (`DESIGN_DIR` of `design`), a compose directory or one of its indexes (`COMPOSE_DIR/NAME`), a session (`COMPOSE_DIR/NAME/SESSION` or its `index.yaml`), or one shard file (`SESSION/shards/<shard>.yaml`, built without merge) (required) |
    | `-S, --session SESSION` | Session to use when INPUT is a directory (default: the last one composed) |
    | `-o, --output-dir BUILD_DIR` | Index directory the plan targets, same as for [`build`](build.md) and [`apply`](apply.md) (required) |

!!! abstract "I/O"
    **Input:** `DESIGN_DIR` of `design` (or `COMPOSE_DIR` of `compose`), with `-S` to pick a session; it resolves to `compose/NAME/SESSION/index.yaml` (see [design - Next Step](design.md#next-step))  
    **Output:** shell scripts in `BUILD_DIR/assets/`, validation report in `BUILD_DIR/logs/`

See [build - Paths](build.md#paths) for the directory layout.

## Advanced Options

| Option | Description |
|--------|-------------|
| `--bp, --base-path DIR` | Base path to resolve relative sample paths |
| `-s, --span TEXT` | Span(s) to preview: single value, comma-separated, or range (e.g. `27-30`) |
| `--sh, --shard TEXT` | Shard(s) to preview (repeatable or comma-separated) |
| `-t, --threads INT` | Number of threads |
| `-NC, --skip-compression` | Skip compression of intermediate files during index building (useful on slow disks) |
| `--limits JSON` | Resource limits used to auto-size threads/partitions when `--threads` is not set (`ram`, `files`, `threads`), and the inputs of one merge (`ram`, `files`, `maps` = `vm.max_map_count`); see [build - Builds and merges](build.md#builds-and-merges) |
| `--safety-margin FLOAT` | Fraction of a detected system limit to use (default: 0.9) |
| `--max-chunks INT` | Max number of chunks a single index is split into; bigger chunks mean fewer build/merge passes but fewer threads. 0 disables the cap (default: 200) |
| `-X, --fail-fast` | Abort on first failure instead of continuing |
| `--keep-previous` | Keep the replaced version of an updated index in `BUILD_DIR/work/SESSION/previous/` instead of deleting it |
| `-O, --offline` | Skip local path validation (useful when exporting scripts for another machine) |

## Description

`plan` validates all sample paths of the session upfront and previews the commands that would be executed by [`apply`](apply.md), without running them or touching the registry. It writes the equivalent shell scripts to `BUILD_DIR/assets/SESSION/` (one per sub-index, `<shard>.sh` with its builds and `<shard>_merge.sh` with its publication, plus `kmhelpers_apply.sh` running them in order; see [build - Builds and merges](build.md#builds-and-merges)) and a validation report to `BUILD_DIR/logs/`.

**Offline mode** - use `--offline` to skip local path validation when generating scripts destined for another machine.

**Filtering** - use `--name` or `--span` to preview only a subset of the declared indices.

## Examples

```bash
# Preview build plan for a definition file
kmhelpers plan coli_db -o coli_build/

# Preview with specific spans
kmhelpers plan coli_db -o coli_build/ -s 28,31

# Preview for specific index names
kmhelpers plan coli_db -o coli_build/ --sh coli_g0

# Skip path validation (for exporting scripts)
kmhelpers plan coli_db -o coli_build/ --offline

# Abort on first error
kmhelpers plan coli_db -o coli_build/ -X
```

## See Also

- [`build`](build.md) - run plan then apply in a single command
- [`apply`](apply.md) - actually build the indices
- [`compose`](compose.md) - generate index definition files
