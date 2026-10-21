# apply

## Synopsis

Build k-mer indices from an index definition file.

!!! abstract "USAGE"
    ```
    kmhelpers apply [OPTIONS] INPUT
    ```

    | Argument | Description |
    |----------|-------------|
    | `INPUT` | The design directory (`DESIGN_DIR` of `design`), a compose directory or one of its indexes (`COMPOSE_DIR/NAME`), a session (`COMPOSE_DIR/NAME/SESSION` or its `index.yaml`), or one shard file (`SESSION/shards/<shard>.yaml`, built without merge) (required) |
    | `-S, --session SESSION` | Session to use when INPUT is a directory (default: the last one composed) |
    | `-o, --output-dir BUILD_DIR` | Index directory: receives the built index, reused across builds and passed to `query -r` (required) |

!!! abstract "I/O"
    **Input:** `DESIGN_DIR` of `design` (or `COMPOSE_DIR` of `compose`), with `-S` to pick a session; it resolves to `compose/NAME/SESSION/index.yaml` (see [design - Next Step](design.md#next-step))  
    **Output:** indices in `BUILD_DIR/<name>/`, registered in `BUILD_DIR/index.json`

See [build - Paths](build.md#paths) for the directory layout.

## Advanced Options
| Option | Description |
|--------|-------------|
| `--bp, --base-path DIR` | Base path to resolve relative sample paths |
| `--sh, --shard TEXT` | Shards to build, as names or glob patterns (repeatable or comma-separated, e.g. `idx_g0_p1`, `'idx_g0_*'`); a part name (`<shard>_<session>`) builds that part only, without merging |
| `--run TEXT` | Build only the kmtricks runs matching these names or glob patterns (`<part>` or `<part>_chunk<N>`), without merging; see [Building chunks separately](apply.md#building-chunks-separately) |
| `--threads INT` | Hidden. Force the number of kmtricks threads instead of sizing them from `--limits` |
| `--limits JSON` | Resource limits used to auto-size threads/partitions when `--threads` is not set (`ram`, `files`, `threads`), and the inputs of one merge (`ram`, `files`, `maps` = `vm.max_map_count`); see [build - Builds and merges](build.md#builds-and-merges) |
| `--safety-margin FLOAT` | Fraction of a detected system limit to use (default: 0.9) |
| `--max-chunks INT` | Max number of kmtricks chunks a shard is built in; bigger chunks mean fewer build/merge passes but fewer threads. 0 disables the cap (default: 64) |
| `-cb, --chunk-budget INT` | K-mer budget of one kmtricks chunk: a chunk of span `s` holds at most `ceil8(budget / base^s)` samples. 0 for no limit (default: `2**37`), see [build - Shards and chunks](build.md#shards-and-chunks) |
| `--keep-previous` | Keep the replaced version of an updated index in `BUILD_DIR/work/SESSION/previous/` instead of deleting it |
| `-NC, --skip-compression` | Skip compression of intermediate files during index building (useful on slow disks) |
| `-SP, --show-progress` | Enable animation that shows the current subindex being built (use in an interactive shell) |
| `-X, --fail-fast` | Abort on first failure instead of continuing |
| `--notify EMAIL` | Send email notification on exit (requires sendmail) |

## Description

`apply` builds the indices of the session and registers them in `BUILD_DIR/index.json` on completion.

**Parent indices** - built automatically when required.

**Filtering** - `--shard` selects shards (all by default) by name or glob pattern: `--shard 'idx_g0_*'` selects every shard of group 0. A pattern that matches no shard is an error. `--run` goes one level down, to the kmtricks runs of a shard, and builds them without merging.

### Building chunks separately

A shard whose new samples don't fit one kmtricks build is built in chunks, `<part>_chunk<N>` (see [build - Shards and chunks](build.md#shards-and-chunks)). `--run` builds only the matching runs and merges nothing, e.g. one chunk per task of a SLURM array; a final `apply --shard` reuses the complete runs and merges them. Every task must use the same `--limits`, `--chunk-budget` and `--max-chunks` as the final apply, so the chunks are cut the same way: `plan` with these options lists the run names.

```bash
# one task per chunk
kmhelpers apply coli_db -o coli_build/ --limits "$LIMITS" --run "coli_g0_p0_initial_chunk${SLURM_ARRAY_TASK_ID}"
# then, once all are done
kmhelpers apply coli_db -o coli_build/ --limits "$LIMITS" --shard coli_g0_p0
```

## Examples

```bash
# Build all indices in a definition file
kmhelpers apply coli_db -o coli_build/

# Build only selected indices by name (comma-separated or repeated flags)
kmhelpers apply coli_db -o coli_build/ --sh coli_g0,coli_g1
kmhelpers apply coli_db -o coli_build/ --sh coli_g0 --sh coli_g1

# Build every shard of group 0 (glob pattern)
kmhelpers apply coli_db -o coli_build/ --sh 'coli_g0_*'

# Resolve sample paths from a base directory
kmhelpers apply coli_db -o coli_build/ --bp /data/samples

# Set threads, show progress, abort on first error
kmhelpers apply coli_db -o coli_build/ --limits '{"threads": 8}' -SP -X

# Notify by email when done
kmhelpers apply coli_db -o coli_build/ --notify user@example.com
```

## See Also

- [`plan`](plan.md) - preview the build plan with path validation
- [`build`](build.md) - run plan then apply in a single command
- [`compose`](compose.md) - generate index definition files
- [`pipeline`](pipeline.md) - run multiple steps in sequence
