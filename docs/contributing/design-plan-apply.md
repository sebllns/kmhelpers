# Design: `plan` prepares, `apply` runs

Status: **implemented** (see `commands/plan.md` and `commands/apply.md` for the reference). No backward compatibility is kept.

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
| `--cluster FILE` (new) | ✔ | | |
| `--pending` (new: list jobs not done) | | ✔ | |
| `--shard` (filter what is planned) | ✔ | | |
| `--task` (select what is run: shards, tasks or jobs) | | ✔ | |
| `--show-progress`, `--notify`, `--fail-fast` | | ✔ | ✔ |

- `apply --run` is removed: `--task` replaces it.
- `build` = `plan` then `apply` on the plan just written (whole shard jobs).

## Shards, chunks and jobs

`plan` describes the work as **tasks**, one per shard part
(`<shard>_<session>`, where `<shard>` is `<name>_g<n>` or
`<name>_g<n>_p<m>`). A task is one session's samples added to one shard:

- its **chunks**: the kmtricks runs (`<part>` or `<part>_chunk<n>`);
- its **merge**: check runs, merge, swap, register, check, clean up (what
  `<shard>_merge.sh` does today).

A task's work is grouped into **jobs**, what `apply --task` and a SLURM
array task run. A job never spans tasks.

A plan *task* is not a SLURM *task*: the SLURM side is always written
"array task". `--chunks-per-job N` sets the grouping:

| `N` | Jobs of a shard with `c` chunks |
|---|---|
| `0` (default) | one job `<shard>`: all chunks, then the merge |
| `N > 0`, `c <= N` | same as `0` |
| `N > 0`, `c > N` | `ceil(c / N)` jobs `<shard>_j<k>` of up to `N` chunks, then a job `<shard>_merge` after all of them |

Chunks of one job run one after the other, each sized by `--limits`.

Example, shard `idx_g0` in 7 chunks with `--chunks-per-job 3`:

```
idx_g0_j0     chunk0 chunk1 chunk2
idx_g0_j1     chunk3 chunk4 chunk5
idx_g0_j2     chunk6
idx_g0_merge  needs idx_g0_j0, idx_g0_j1, idx_g0_j2
```

## The plan bundle

Written to `BUILD_DIR/assets/SESSION/`, one directory per shard:

```
assets/initial/
  plan.yaml                       # session manifest (below)
  slurm/                          # with --cluster only (see Cluster)
    jobs.txt  build.sbatch  submit.sh
  idx_g0/
    idx_g0_initial.sh         # one script per chunk
    idx_g0_initial.fof        # its sample list
    merge.sh                      # the merge of the shard
    merge/                        # runs.tsv and the register .tsv of each merge step
    jobs/                         # only with --chunks-per-job N > 0
      j0.sh  j1.sh  merge.sh      # each calls `kmhelpers apply --task <job>`
  idx_g1/
    ...
```

- Every file of a shard lives in its directory: a job never spans shards.
- Run files keep the full run name (`<part>_chunk<n>.sh`), so a file name
  alone matches log lines and `--task` values.
- With `--chunks-per-job 0` there is no `jobs/`: the shard is the job
  (its run scripts, then `merge.sh`).
- An index definition outside a span registry is its own target: it gets
  its own directory, named after it.
- Logs follow the same layout: `BUILD_DIR/logs/<shard>/` holds the
  `kmtricks.log` of its chunks and the logs of its merge.

`plan.yaml`:

```yaml
type: plan
fingerprint: sha256:...        # see Staleness
created: 2026-10-23T10:00:00
definition: /data/db/compose/idx/initial/index.yaml
options:
  limits: {ram: 128849018880, threads: 24, ...}   # resolved values
  chunks_per_job: 3
  ...
tasks:
  idx_g0_initial:
    shard: idx_g0                 # target index in BUILD_DIR
    dir: idx_g0/
    samples: 448
    partitions: 64
    minim_size: 10
    threads: 24
    chunks:                         # dir/<chunk>.sh, dir/<chunk>.fof
      idx_g0_initial_chunk0: {samples: 64}
      ...
      idx_g0_initial_chunk6: {samples: 64}
    merge:
      script: merge.sh
      expects: {target_registered: false}   # or {partitions: 64, minim_size: 10}
      mode: merge                   # move: a single chunk and no current version
      max_inputs: 4
      steps:
        - {name: idx_g0__sub1_0, inputs: [idx_g0_initial_chunk0, ..., chunk3]}
        - {name: idx_g0__sub1_1, inputs: [idx_g0_initial_chunk4, ..., chunk6]}
        - {name: idx_g0, inputs: [idx_g0__sub1_0, idx_g0__sub1_1]}
    jobs:
      idx_g0_j0: [idx_g0_initial_chunk0, idx_g0_initial_chunk1, idx_g0_initial_chunk2]
      idx_g0_j1: [idx_g0_initial_chunk3, idx_g0_initial_chunk4, idx_g0_initial_chunk5]
      idx_g0_j2: [idx_g0_initial_chunk6]
      idx_g0_merge: [merge]       # after every other job of the shard
```

Done tests are implied: a chunk is done when its run directory is complete
(`chunk_problems`), a merge when its `done` marker exists and the shard is
registered.

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
shard's merge.

## What `apply` does

1. Load `plan.yaml`; fail if missing.
2. Recompute the fingerprint; refuse if it differs ("plan is stale, run
   `kmhelpers plan` again").
3. Select jobs: all (in dependency order), or those `--task` matches: a
   pattern matching a shard or a task selects all its jobs, one matching a
   job selects that job.
4. For a `<shard>_merge` job, refuse if another job of the shard is not done.
5. For each chunk, then the merge, of the job:
   - done: skip (`reused`);
   - chunk with an incomplete run directory: delete it, rebuild;
   - merge: check `expects` against the live registry, refuse on mismatch
     (stale plan);
   - run its script, log to `BUILD_DIR/logs/<shard>/`, stream it with
     `--show-progress`.
6. Write the report (per task: each chunk's status, action, duration,
   `kmtricks.log` info; the merge details), updated after each step;
   `--notify` at exit.

Chunk and merge scripts are idempotent on their own (guards as merges have today), so
running `<shard>/<chunk>.sh` or `<shard>/merge.sh` by hand is also safe.

## Staleness

The fingerprint hashes:

- the definition file and `COMPOSE_DIR/NAME/layout.yaml`;
- the resolved sample list (names and paths) of every planned definition;
- the effective plan options (resolved limits, budgets, flags) and the
  `--cluster` file;
- the kmhelpers version.

The registry is not hashed: it changes while jobs publish. It is checked
per task merge through `expects` instead.

## Cluster (`plan --cluster FILE`)

`--cluster` takes a YAML file describing the scheduler and the resources of
each kind of job. `plan` then writes the submission files next to the plan.

```yaml
type: slurm                     # only slurm for now
partition: compute
time: 2-00:00:00
exclude: [node01]
account: null                   # optional: account, qos, constraint
max_parallel: 8                 # build array tasks running at once (%8)
output: logs/slurm/%x_%A_%a.out # relative to BUILD_DIR
setup: |                        # run before kmhelpers in every job
  export PATH=/path/to/kmhelpers/bin:$PATH
extra: []                       # other sbatch options, as is
jobs:                           # resources per kind of job
  build: {cpus: 24, mem: 120G}
  merge: {cpus: 24, mem: 120G}
  check: {cpus: 1, mem: 4G, time: "1:00:00"}
limits: {files: 131072, maps: 65530}  # optional: compute-node limits, see below
```

- Keys under `jobs.<kind>` override the top-level ones (`partition`,
  `time`, ...) for that kind. Unknown keys are an error.
- **The cluster file is the source of the limits**: `plan` sizes chunks from
  `jobs.build` (`threads = cpus`, `ram = mem`) and merges from `jobs.merge`,
  plus `limits:` for what the allocation does not tell. The allocation
  cannot differ from the plan. `--limits` with `--cluster` is an error.
- **`limits.files` and `limits.maps`** are node settings, not part of an
  allocation. Without `limits:`, `plan` detects them on the node it runs on;
  set them only when the compute nodes differ from it:
  - `files`: the **hard** open-files limit (`ulimit -Hn`): kmhelpers and its
    scripts raise the soft limit to it (`ulimit -Sn "$(ulimit -Hn)"` in every
    generated script);
  - `maps`: `vm.max_map_count` (`cat /proc/sys/vm/max_map_count`), per node,
    not propagated by SLURM;
  - read them on a compute node with
    `srun -p <partition> -c 1 --mem=1G -t 5 bash -c 'ulimit -Hn; cat /proc/sys/vm/max_map_count'`.
- The resolved file is copied into `plan.yaml` (`cluster:`) and hashed in the
  fingerprint.
- The same file can be given in the `-C` config (`plan: {cluster: ...}`).

Writes `slurm/`:

```
jobs.txt          build jobs, one per line
build.sbatch      array: array task i runs `kmhelpers apply --task <line i>`
merge.sbatch      `kmhelpers apply --task <shard>_merge`
check.sbatch      `kmhelpers manage -r BUILD_DIR check`
submit.sh         submits what `apply --pending` lists (safe to run again):
                  1. the build array, %max_parallel
                  2. each merge job, --dependency=afterok:<array>_<array task
                     ids of its shard>
                  3. the check job, after every merge
```

- With `--chunks-per-job 0` there is no merge job: one array task per shard,
  no dependency; the check job waits for the whole array.
- An array longer than the cluster `MaxArraySize` is split by `submit.sh`.

## Removed

- `apply` sizing options, `--run`, and planning inside `apply`.
- Parts registered separately by older kmhelpers (`absorbed` in
  `IndexOps._publish` and `IndexExecutor.publish`).
- Old-layout symlinks: `--keep-link` on unregister, symlink resolution in
  `IndexExecutor._remove`.
- `kmhelpers_apply.sh` and the flat `<shard>.sh` / `<shard>_merge.sh` /
  `*.fof` / `*.tsv` files: replaced by the per-shard directories.

## Implementation steps

1. `IndexOps`: build the plan (tasks, chunks, jobs, `expects`, fingerprint) without
   executing; write `plan.yaml` and the per-shard directories. Remove the
   legacy paths.
2. Chunks: guard in each chunk script (complete run: skip, incomplete:
   rebuild), as merges are guarded.
3. New executor for `apply`: load, check fingerprint, select, check
   `needs`/`expects`, run scripts, report, progress from logs.
4. CLI: move options, add `--chunks-per-job`, `--task`, `--pending`,
   `--cluster`; `build` = plan + apply.
5. `--cluster`: schema and validation, limits from the job resources,
   SLURM writer.
6. Tests: e2e plan/apply/resume, stale plan, `expects` mismatch, job grouping
   (N = 0, N >= c, N < c), cluster file validation, SLURM files.
7. Docs: `commands/plan.md`, `apply.md`, `build.md`.
