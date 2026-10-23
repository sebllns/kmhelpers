# apply

## Synopsis

Run the plan written by [`plan`](plan.md): build, merge and register the indices.

!!! abstract "USAGE"
    ```
    kmhelpers apply [OPTIONS] INPUT
    ```

    | Argument | Description |
    |----------|-------------|
    | `INPUT` | The INPUT given to `plan`: the design directory, a compose directory or one of its indexes, a session or its `index.yaml`, or one shard file (required) |
    | `-s, --session SESSION` | Session to use when INPUT is a directory (default: the last one composed) |
    | `-o, --output-dir BUILD_DIR` | The BUILD_DIR given to `plan` (required) |

!!! abstract "I/O"
    **Input:** `BUILD_DIR/assets/SESSION/plan.yaml`, written by `plan` for the same INPUT and BUILD_DIR  
    **Output:** indices in `BUILD_DIR/<name>/`, registered in `BUILD_DIR/index.json`

See [build - Paths](build.md#paths) for the directory layout.

## Advanced Options
| Option | Description |
|--------|-------------|
| `--sh, --shard TEXT` | Run only the jobs of these shards, as names or glob patterns (repeatable or comma-separated) |
| `--job TEXT` | Run only the jobs matching these names or glob patterns: `<shard>` (a whole shard), `<shard>_j<k>` (some of its chunks) or `<shard>_merge` (see [plan - Jobs](plan.md#jobs)) |
| `--pending` | Print the jobs not done yet, one per line, and run nothing |
| `--sp, --show-progress` | Show the run being built (use in an interactive shell) |
| `-x, --fail-fast` | Abort on first failure instead of going on with the other shards |
| `--notify EMAIL` | Send email notification on exit (requires sendmail), with the log and the apply report attached |

`apply` takes no sizing option (`--limits`, `--chunk-budget`, ...): they are decisions of the plan.

## Description

`apply` loads the plan and refuses it when it is stale: an input file changed since `plan` (definition, shard files, `layout.yaml`, sample lists, `--cluster` file), or another kmhelpers version made it. Run `plan` again then.

Then it runs the selected jobs (all by default), in order. Each step is checked before it runs, so a job can be run again after an interruption, or by several processes in turn:

- a shard is **done** when it is registered and holds every sample of the plan's chunks: its jobs do nothing;
- a **chunk** is skipped when its kmtricks run is complete (`reused`), else its script deletes what an earlier attempt left and builds it;
- a **merge** needs every chunk of its shard complete; it checks that the registry is as `plan` saw it (`expects`), or as an interrupted run of this same merge leaves it, and refuses otherwise.

A failed step stops its shard; the other shards go on, unless `--fail-fast`. Logs are in `BUILD_DIR/logs/<shard>/` (`<run>.log` with the `kmtricks` output and its resource use, `merge.log`).

**Report** - `BUILD_DIR/logs/kmhelpers_apply_<timestamp>.yaml`: per shard, for each kmtricks run whether it was built, reused or already published, its duration, peak RSS, CPU efficiency and share of the RAM limit (from its log); the merge, its duration and size on disk. It is written after each job, with status `RUNNING` until the end, so a running or killed apply leaves its report so far. See [build - Report](build.md#report).

### Running jobs separately

With `plan --chunks-per-job N`, the chunks of a shard are split into jobs that can run at the same time, e.g. as the tasks of a SLURM array, then the merge job of the shard. `plan --cluster` writes the SLURM files submitting them (see [plan - Cluster](plan.md#cluster)); by hand:

```bash
kmhelpers plan coli_db -o coli_build/ --chunks-per-job 4
kmhelpers apply coli_db -o coli_build/ --pending          # the jobs to run
kmhelpers apply coli_db -o coli_build/ --job coli_g0_j0   # one per array task
kmhelpers apply coli_db -o coli_build/ --job coli_g0_merge
```

## Examples

```bash
# Run the whole plan
kmhelpers apply coli_db -o coli_build/

# Run the jobs of some shards
kmhelpers apply coli_db -o coli_build/ --sh coli_g0,coli_g1
kmhelpers apply coli_db -o coli_build/ --sh 'coli_g0_*'

# Show progress, abort on first error
kmhelpers apply coli_db -o coli_build/ --sp -x

# Notify by email when done
kmhelpers apply coli_db -o coli_build/ --notify user@example.com
```

## See Also

- [`plan`](plan.md) - decide everything and write the plan
- [`build`](build.md) - run plan then apply in a single command
- [`compose`](compose.md) - generate index definition files
- [`pipeline`](pipeline.md) - run multiple steps in sequence
