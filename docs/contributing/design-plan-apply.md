# Design: `plan` prepares, `apply` runs

Status: **draft, for approval**. No backward compatibility is kept.

## Goals

- `plan` takes every build decision and writes a runnable bundle.
- `apply` only runs and monitors that bundle: it has no sizing option, and
  cannot run without a plan.
- What was reviewed in `plan` is what `apply` runs; a stale plan is refused.
- The unit of a job is configurable: a whole shard by default, or N chunks.

## Commands and options

| Option | `plan` | `apply` | `build` |
|---|:-:|:-:|:-:|
| `INPUT`, `-o BUILD_DIR`, `--session` | ✔ | ✔ | ✔ |
| `--limits`, `--safety-margin`, `--threads` | ✔ | | ✔ |
| `--chunk-budget`, `--max-chunks` | ✔ | | ✔ |
| `--chunks-per-job N` (new) | ✔ | | |
| `--base-path`, `--skip-compression`, `--keep-previous` | ✔ | | ✔ |
| `--offline` | ✔ | | |
| `--slurm`, `--slurm-opts` (new) | ✔ | | |
| `--shard` (filter what is planned) | ✔ | | |
| `--shard`, `--job` (select what is run) | | ✔ | |
| `--show-progress`, `--notify`, `--fail-fast` | | ✔ | ✔ |

- `apply --run` is removed: `--job` replaces it.
- `build` = `plan` then `apply` on the plan just written (whole shard jobs).

## Units and jobs

`plan` always describes the work at the finest level, as **units**:

- one **run unit** per kmtricks run (`<part>` or `<part>_chunk<n>`);
- one **merge unit** per shard: check runs, merge, swap, register, check,
  clean up (what `<shard>_merge.sh` does today).

Units are grouped into **jobs**, what `apply --job` and a SLURM task run.
`--chunks-per-job N` sets the grouping:

| `N` | Jobs of a shard with `c` runs |
|---|---|
| `0` (default) | one job `<shard>`: all runs, then the merge |
| `N > 0`, `c <= N` | same as `0` |
| `N > 0`, `c > N` | `ceil(c / N)` jobs `<shard>_j<k>` of up to `N` runs, then a job `<shard>_merge` depending on all of them |

Runs of one job run one after the other, each sized by `--limits`.

Example, shard `metaG_g0` in 7 chunks with `--chunks-per-job 3`:

```
metaG_g0_j0     chunk0 chunk1 chunk2
metaG_g0_j1     chunk3 chunk4 chunk5
metaG_g0_j2     chunk6
metaG_g0_merge  needs metaG_g0_j0, metaG_g0_j1, metaG_g0_j2
```

## The plan bundle

Written to `BUILD_DIR/assets/SESSION/`:

```
plan.yaml          manifest (below)
units/<unit>.sh    one script per unit
jobs/<job>.sh      calls `kmhelpers apply --job <job>` (for running by hand)
*.fof, *.tsv       sample lists and run lists, as today
slurm/             with --slurm only (see SLURM)
```

`plan.yaml`:

```yaml
type: plan
fingerprint: sha256:...        # see Staleness
created: 2026-10-23T10:00:00
definition: bioswot/metaG/compose/metaG/initial/index.yaml
limits: {ram: 128849018880, threads: 24, ...}   # resolved values
chunks_per_job: 3
units:
  metaG_g0_initial_chunk0:
    kind: run
    script: units/metaG_g0_initial_chunk0.sh
    partitions: 64
    samples: 512
    done: {complete_run: work/initial/runs/metaG_g0_initial_chunk0}
  metaG_g0:
    kind: merge
    script: units/metaG_g0.sh
    needs: [metaG_g0_initial_chunk0, ...]
    expects: {target_registered: false}             # or {partitions: 64, minim_size: 15}
    done: {marker: work/initial/merges/metaG_g0/metaG_g0/done, registered: metaG_g0}
jobs:
  metaG_g0_j0: {units: [metaG_g0_initial_chunk0, ...]}
  metaG_g0_merge: {units: [metaG_g0], needs: [metaG_g0_j0, metaG_g0_j1, metaG_g0_j2]}
```

## What `plan` decides

All the decisions `IndexOps._run` takes today, once, against the registry
as it is at plan time:

- partitions, threads, minimizer size, chunk split (`resolve_build_params`);
- alignment with a registered target (`IndexExecutor.align_with`);
- skip of definitions already registered or already in their target;
- refusal of a part whose samples partly overlap its target;
- move or merge, and the merge tree (`MergeLimits`, `max_inputs`, `merge_tree`);
- the backup name of the replaced version.

Each decision that depends on the registry is written as `expects` on the
merge unit.

## What `apply` does

1. Load `plan.yaml`; fail if missing.
2. Recompute the fingerprint; refuse if it differs ("plan is stale, run
   `kmhelpers plan` again").
3. Select jobs: all (in dependency order), `--shard` (the jobs of these
   shards), or `--job`.
4. For each job, refuse if a job it `needs` is not done.
5. For each unit of the job:
   - done test true: skip (`reused`);
   - run unit with an incomplete run directory: delete it, rebuild;
   - merge unit: check `expects` against the live registry, refuse on
     mismatch (stale plan);
   - run the unit script, log to `BUILD_DIR/logs/`, stream it with
     `--show-progress`.
6. Write the report (per unit: status, action, duration, `kmtricks.log`
   info, merge details), updated after each unit; `--notify` at exit.

Unit scripts are idempotent on their own (guards as merges have today), so
running `units/<unit>.sh` by hand is also safe.

## Staleness

The fingerprint hashes:

- the definition file and `COMPOSE_DIR/NAME/layout.yaml`;
- the resolved sample list (names and paths) of every planned definition;
- the effective plan options (resolved limits, budgets, flags);
- the kmhelpers version.

The registry is not hashed: it changes while jobs publish. It is checked
per merge unit through `expects` instead.

## SLURM (`plan --slurm`)

Writes `slurm/`:

```
jobs.txt          one job name per line (array index = line number - 1)
build.sbatch      array: task i runs `kmhelpers apply --job <line i>`
submit.sh         submits the array, then each merge job with
                  --dependency=afterok:<array>_<task ids of its shard>
```

- With `--chunks-per-job 0` there is no merge job: one array task per shard,
  no dependency.
- `-c` and `--mem` come from the resolved `--limits` (threads, ram), so the
  allocation cannot differ from what was planned.
- `--slurm-opts` is passed as is: partition, time, exclusions, output path,
  e.g. `--slurm-opts "-p long -t 10-00:00:00 --exclude=node59"`.

## Removed

- `apply` sizing options, `--run`, and planning inside `apply`.
- Parts registered separately by older kmhelpers (`absorbed` in
  `IndexOps._publish` and `IndexExecutor.publish`).
- Old-layout symlinks: `--keep-link` on unregister, symlink resolution in
  `IndexExecutor._remove`.
- `kmhelpers_apply.sh` and the per-shard `<shard>.sh` / `<shard>_merge.sh`:
  replaced by `units/` and `jobs/`.

## Implementation steps

1. `IndexOps`: build the plan (units, jobs, `expects`, fingerprint) without
   executing; write `plan.yaml` and unit scripts. Remove the legacy paths.
2. Run units: guard in each run script (complete run: skip, incomplete:
   rebuild), as merges are guarded.
3. New executor for `apply`: load, check fingerprint, select, check
   `needs`/`expects`, run scripts, report, progress from logs.
4. CLI: move options, add `--chunks-per-job`, `--job`, `--slurm`,
   `--slurm-opts`; `build` = plan + apply.
5. `--slurm` writer.
6. Tests: e2e plan/apply/resume, stale plan, `expects` mismatch, job grouping
   (N = 0, N >= c, N < c), SLURM files.
7. Docs: `commands/plan.md`, `apply.md`, `build.md`;
   `bioswot/scripts/build.sbatch` becomes `plan --slurm` + `submit.sh`.
