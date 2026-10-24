# apply

## Synopsis

Run the plan written by [`plan`](plan.md): build and publish the indices.

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
| `--task TEXT` | Run only what matches these names or glob patterns (repeatable or comma-separated): a shard (`idx_g0`) or its task (`idx_g0_initial`) runs all its jobs; a job runs alone, `<shard>_j<k>` (some of its chunks) or `<shard>_publish` (see [plan - Jobs](plan.md#jobs) and [Selecting what runs](#selecting-what-runs)) |
| `--pending` | Print the jobs not done yet, one per line, and run nothing |
| `--status` | Print the status of every step, per shard, write it to `progress.yaml`, and run nothing; with `--notify`, mail it (see [Progress](#progress)) |
| `--sp, --show-progress` | One line per shard: progress bar of its steps, steps running, colored end status (see [Following a build](#following-a-build)); with `--status`, follow a cluster build until it ends |
| `--interval SECONDS` | With `--status --sp`: seconds between two reads of a cluster build (default: 30) |
| `-x, --fail-fast` | Abort on first failure instead of going on with the other shards |
| `--notify EMAIL` | Send email notifications (requires sendmail), with the progress, the log and the apply report attached |
| `--notify-level global\|shard` | `global` (default): one mail at the end; `shard`: also one mail per shard when it ends (see [build - Notifications](build.md#notifications)) |

`apply` takes no sizing option (`--limits`, `--chunk-budget`, ...): they are decisions of the plan.

## Description

`apply` loads the plan and refuses it when it is stale: an input file changed since `plan` (definition, shard files, `layout.yaml`, sample lists, `--cluster` file), or another kmhelpers version made it. Run `plan` again then.

Then it runs the selected jobs (all by default), in order. Each step is checked before it runs, so a job can be run again after an interruption, or by several processes in turn:

- a shard is **done** when it is registered and holds every sample of the plan's chunks: its jobs do nothing;
- a **chunk** is skipped when its kmtricks run is complete (`reused`), else its script deletes what an earlier attempt left and builds it;
- a **publish** step needs every chunk of its shard complete; it checks that the registry is as `plan` saw it (`expects`), or as an interrupted run of this same publish step leaves it, and refuses otherwise.

A failed step stops its shard; the other shards go on, unless `--fail-fast`. Logs are in `BUILD_DIR/logs/<shard>/` (`<run>.log` with the `kmtricks` output and its resource use, `publish.log`).

### Following a build

`--sp, --show-progress` draws one line per shard, once its first step has started:

```
⣾ idx_g0  [■■■■■■      ] 6/11 (8m3s)   8 running: chunk2 (4m10s), chunk5 (3m12s), chunk8 (52s), ...
⣽ idx_g1  [■■■■■■■■■■■ ] 10/11 (12m40s) publish (3m4s)
✔ idx_g2  [■■■■■■■■■■■■] 8/8  (25m14s) SUCCESS
✘ idx_g3  [■■■         ] 3/9  (6m2s)   FAILED chunk3 (log: logs/idx_g3/idx_g3_initial_chunk3.log), 2 still running
```

- the bar and the count are the steps of the shard done: its kmtricks runs (`chunk<N>`, or
  `run` when it is built in one run) and its `publish` step; the time is the shard's, since its
  first step started;
- several chunks of a shard run at once on a cluster with `plan --chunks-per-job N` (one
  per array task): the line shows how many, and the 3 oldest with their time;
- an ended shard keeps its line: `SUCCESS` (green), `FAILED` (red), `LOST` or `CANCELLED`
  (yellow), with the failed step and its log.

While no shard has started yet (jobs still queued), a spinner shows `waiting for the first step to start (N shards pending)`.

In a terminal, the lines are redrawn in place (log lines print above them); otherwise
(redirected to a file, a SLURM job), a shard's line is printed each time one of its steps
ends.

For a cluster build, `apply --status --sp` (or `build --hpc --sp` right after the
submission) draws the same lines, read again every `--interval` seconds, until no shard is
running or waiting on a job: it exits 0 when every shard is `SUCCESS`, 1 otherwise. Ctrl-C
stops watching; the jobs go on.

### Progress

Each step `apply` runs is recorded in `BUILD_DIR/assets/SESSION/<shard>/state/<step>.json` (status, job, node, times, log, error), and `BUILD_DIR/assets/SESSION/progress.yaml` is rewritten after each one. `apply --status` prints it, refreshed:

| Status | Meaning |
|--------|---------|
| `SUCCESS` | the run is complete, or the shard holds the samples of its task (from the build directory, whatever was recorded) |
| `FAILED` | the step failed: its log and the last line of its error |
| `CANCELLED` | the job got `SIGTERM` (`scancel`, time limit) during the step |
| `RUNNING` | started by a job (`job`, node, start time) |
| `LOST` | recorded as running, but its job is no longer in `squeue`: it ended without a status (out of memory, node failure); see its SLURM log |
| `PENDING` | not run yet; `(job X)` when `submit.sh` submitted it, `ended without running it` when that job is gone (a step before it failed, or a dependency was cancelled): submit again |

`--status` exits 0 whatever the status; the summary line gives the overall one (`SUCCESS`, `FAILED`, `RUNNING`, `PENDING`).

**Report** - `BUILD_DIR/logs/kmhelpers_apply_<timestamp>.yaml`: per shard, for each kmtricks run whether it was built, reused or already published, its duration, peak RSS, CPU efficiency and share of the RAM limit (from its log); how it was published, its duration and size on disk. It is written after each job, with status `RUNNING` until the end, so a running or killed apply leaves its report so far. See [build - Report](build.md#report).

### Selecting what runs

`--task` takes names or glob patterns (repeatable or comma-separated). A pattern selects every job whose name, task or shard it matches, so a shard or task name runs all the jobs of that shard, and a job name runs only that job:

| `--task` | Runs |
|----------|------|
| `idx_g0` or `idx_g0_initial` | every job of that shard (shard or task name) |
| `'idx_g0_*'` | every job of the group-0 shards |
| `idx_g0_j1` | that one job |
| `'idx_g0_j*'` | the shard's chunk jobs, not its publish job |
| `'*_publish'` | every publish job |

A pattern that matches nothing is a warning; only no match at all is an error (`No task matches ...`). Job names are listed in `plan.yaml` (`jobs:` of each task), and `--pending` prints those not done yet.

### Running jobs separately

With `plan --chunks-per-job N`, the chunks of a shard are split into jobs that can run at the same time, e.g. as the tasks of a SLURM array, then the publish job of the shard. `plan --cluster` writes the SLURM files submitting them (see [plan - Cluster](plan.md#cluster)); by hand:

```bash
kmhelpers plan coli_db -o coli_build/ --chunks-per-job 4
kmhelpers apply coli_db -o coli_build/ --pending          # the jobs to run
kmhelpers apply coli_db -o coli_build/ --task coli_g0_j0  # one per array task
kmhelpers apply coli_db -o coli_build/ --task coli_g0_publish
```

## Examples

```bash
# Run the whole plan
kmhelpers apply coli_db -o coli_build/

# Run the jobs of some shards
kmhelpers apply coli_db -o coli_build/ --task coli_g0,coli_g1
kmhelpers apply coli_db -o coli_build/ --task 'coli_g0_*'

# Show progress, abort on first error
kmhelpers apply coli_db -o coli_build/ --sp -x

# Notify by email when done
kmhelpers apply coli_db -o coli_build/ --notify user@example.com

# Where every shard and step stands
kmhelpers apply coli_db -o coli_build/ --status

# Follow a cluster build, one line per shard, until it ends
kmhelpers apply coli_db -o coli_build/ --status --sp
```

## See Also

- [`plan`](plan.md) - decide everything and write the plan
- [`build`](build.md) - run plan then apply in a single command
- [`compose`](compose.md) - generate index definition files
- [`pipeline`](pipeline.md) - run multiple steps in sequence
