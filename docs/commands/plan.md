# plan

## Synopsis

Decide how to build the indices of a definition file, and write the plan: `plan.yaml` and the scripts of every shard, which [`apply`](apply.md) runs.

!!! abstract "USAGE"
    ```
    kmhelpers plan [OPTIONS] INPUT
    ```

    | Argument | Description |
    |----------|-------------|
    | `INPUT` | The design directory (`DESIGN_DIR` of `design`), a compose directory or one of its indexes (`COMPOSE_DIR/NAME`), a session (`COMPOSE_DIR/NAME/SESSION` or its `index.yaml`), or one shard file (`SESSION/shards/<shard>.yaml`, built without merge) (required) |
    | `-s, --session SESSION` | Session to use when INPUT is a directory (default: the last one composed) |
    | `-o, --output-dir BUILD_DIR` | Index directory the plan targets, same as for [`build`](build.md) and [`apply`](apply.md) (required) |

!!! abstract "I/O"
    **Input:** `DESIGN_DIR` of `design` (or `COMPOSE_DIR` of `compose`), with `-s` to pick a session; it resolves to `compose/NAME/SESSION/index.yaml` (see [design - Next Step](design.md#next-step))  
    **Output:** `BUILD_DIR/assets/SESSION/plan.yaml`, one directory of scripts per shard (`BUILD_DIR/assets/SESSION/<shard>/`), with `--cluster` the SLURM files (`BUILD_DIR/assets/SESSION/slurm/`), report in `BUILD_DIR/logs/` (see [build - Report](build.md#report))

See [build - Paths](build.md#paths) for the directory layout.

## Advanced Options

| Option | Description |
|--------|-------------|
| `--bp, --base-path DIR` | Base path to resolve relative sample paths |
| `--sh, --shard TEXT` | Shards to plan, as names or glob patterns (repeatable or comma-separated, e.g. `idx_g0_p1`, `'idx_g0_*'`); a part name (`<shard>_<session>`) plans that part as its own index |
| `--cpj, --chunks-per-job INT` | Chunks of a shard one job builds: 0 (default) for one job per shard, its chunks then its merge; else jobs `<shard>_j<k>` of up to N chunks, then a job `<shard>_merge` (see [Jobs](#jobs)) |
| `--cluster FILE` | YAML file of the scheduler and the resources of each kind of job: sizes the plan from them (instead of `--limits`) and writes the SLURM files (see [Cluster](#cluster)) |
| `--threads INT` | Hidden. Force the number of kmtricks threads instead of sizing them from `--limits` |
| `--ncp, --skip-compression` | Skip compression of intermediate files during index building (useful on slow disks) |
| `--limits JSON` | Resource limits used to auto-size threads/partitions when `--threads` is not set, for the shard's k-mer occurrences (see [compose - Partitioning](compose.md#description)) (`ram`, `files`, `threads`), and the inputs of one merge (`ram`, `files`, `maps` = `vm.max_map_count`); see [build - Builds and merges](build.md#builds-and-merges) |
| `--safety-margin FLOAT` | Fraction of a detected system limit, or of a `--cluster` job's memory, to use (default: 0.9) |
| `--max-chunks INT` | Max number of kmtricks chunks a shard is built in; bigger chunks mean fewer build/merge passes but fewer threads. 0 disables the cap (default: 64) |
| `--cb, --chunk-budget INT` | K-mer budget of one kmtricks chunk: a chunk of span `s` holds at most `ceil8(budget / base^s)` samples. 0 for no limit (default: `2**37`), see [build - Shards and chunks](build.md#shards-and-chunks) |
| `-x, --fail-fast` | Abort on first failure instead of continuing |
| `--keep-previous` | Keep the replaced version of an updated index in `BUILD_DIR/work/SESSION/previous/` instead of deleting it |
| `--off, --offline` | Skip local path validation (useful when exporting scripts for another machine) |

## Description

`plan` validates all sample paths of the session and takes every build decision: partitions, threads, chunks, merges and jobs, from the resource limits and the registry as it is. It builds nothing and touches no registry. [`apply`](apply.md) then runs the plan as it is: it has no sizing option.

```
BUILD_DIR/assets/SESSION/
  plan.yaml                     the plan (below)
  slurm/                        with --cluster
  <shard>/
    <part>.sh, <part>.fof       one script per kmtricks run (or <part>_chunk<N>.sh)
    merge.sh                    the merge of the shard: check, merge, publish, check, clean
    merge/                      the run list and the inputs of each merge step
```

A shard directory is emptied and rewritten each time it is planned. Every script can be run again after an interruption: a run script does nothing when its samples are already published or its run is complete, and deletes and rebuilds an incomplete run.

**plan.yaml** - one **task** per part (`<shard>_<session>`): one session's samples added to one shard.

```yaml
type: plan
kmhelpers: 0.8.0
definition: /db/compose/idx/initial/index.yaml
fingerprint: {files: {<input file>: <sha256>, ...}}
options: {limits: {...}, chunks_per_job: 3, ...}
tasks:
  idx_g0_initial:
    shard: idx_g0             # the index in BUILD_DIR
    dir: idx_g0/
    samples: 448
    partitions: 64
    minim_size: 10
    threads: 24
    chunks: {idx_g0_initial_chunk0: {samples: 64}, ...}
    merge:
      script: merge.sh
      expects: {registered: false, samples: 0}   # the registry as plan saw it
      mode: merge             # move: a single run and no current version
      max_inputs: 4
      steps: [...]
    jobs:
      idx_g0_j0: [idx_g0_initial_chunk0, idx_g0_initial_chunk1, idx_g0_initial_chunk2]
      ...
      idx_g0_merge: [merge]
```

The **fingerprint** holds the input files the plan was made from: the definition, its shard files, `layout.yaml`, the sample lists and the `--cluster` file. `apply` refuses the plan when one of them changed, or when it was made by another kmhelpers version.

**Report** - `BUILD_DIR/logs/kmhelpers_plan_<timestamp>.yaml`: per shard and part, the build parameters (with where the partition count comes from), the kmtricks runs and chunks planned, the merge steps and their expected memory, and the scripts; plus the limits the sizing used, the host and the SLURM job. See [build - Report](build.md#report).

**Offline mode** - use `--offline` to skip local path validation when generating scripts destined for another machine.

**Filtering** - `--shard` selects shards (all by default) by name or glob pattern: `--shard 'idx_g0_*'` selects every shard of group 0. A pattern that matches no shard is a warning; only no match at all is an error. The plan then holds only these shards.

### Jobs

A job is what `apply --task <job>` and a SLURM array task run. With `--chunks-per-job 0` (default), a shard is one job, named after it: its chunks one after the other, then its merge. With `--chunks-per-job N`, a shard of more than N chunks gets `ceil(chunks / N)` jobs `<shard>_j<k>` of up to N chunks, which can run at the same time on several nodes, then `<shard>_merge`, which runs once they are all done.

### Cluster

`--cluster FILE` sizes the plan from the resources of the jobs that will run it, and writes the files submitting them, to `BUILD_DIR/assets/SESSION/<type>/`. `type` is required and selects the scheduler: only `slurm` for now; another type is refused before anything is planned or written.

```yaml
type: slurm
partition: compute
time: 2-00:00:00
exclude: [node01]
max_parallel: 8                 # build array tasks running at once
output: logs/slurm/%x_%A_%a.out # relative to BUILD_DIR
setup: |                        # run before kmhelpers in every job
  export PATH=/path/to/kmhelpers/.env/bin:$PATH
extra: []                       # other sbatch options, as is
jobs:                           # resources per kind of job
  build: {cpus: 24, mem: 120G}
  merge: {cpus: 24, mem: 120G}
  check: {cpus: 1, mem: 4G, time: "1:00:00"}
limits: {files: 131072, maps: 65530}   # optional, see below
```

- Keys under `jobs.<kind>` (`partition`, `time`, `exclude`, `account`, `qos`, `constraint`, `cpus`, `mem`, `extra`) override the top-level ones for that kind of job. Unknown keys are an error.
- Chunks are sized from `jobs.build` (threads = `cpus`, RAM = `mem` x `--safety-margin`), merges from `jobs.merge`. `--limits` with `--cluster` is an error.
- `limits.files` and `limits.maps` are node settings, not part of an allocation: without them, they are detected on the node `plan` runs on. Set them when the compute nodes differ: `files` is the **hard** open-files limit (`ulimit -Hn`; kmhelpers and its scripts raise the soft limit to it), `maps` is `vm.max_map_count`. Read them on a compute node with `srun -p <partition> -c 1 --mem=1G -t 5 bash -c 'ulimit -Hn; cat /proc/sys/vm/max_map_count'`.

`plan` writes `BUILD_DIR/assets/SESSION/slurm/`:

| File | Runs |
|------|------|
| `jobs.txt` | the build jobs, one per line |
| `build.sbatch` | an array task: one build job (`apply --task`) |
| `merge.sbatch` | one merge job (`apply --task <shard>_merge`) |
| `check.sbatch` | `manage check` of the registry |
| `submit.sh` | submits the jobs `apply --pending` lists: the build array (`%max_parallel`, split at the cluster `MaxArraySize`), each merge job after the array tasks of its own shard, then the check job after everything. Safe to run again: only what is not done is submitted |

## Examples

```bash
# Plan a definition file
kmhelpers plan coli_db -o coli_build/

# Plan every shard of group 0 (glob pattern)
kmhelpers plan coli_db -o coli_build/ --sh 'coli_g0_*'

# Jobs of up to 4 chunks
kmhelpers plan coli_db -o coli_build/ --chunks-per-job 4

# Size the plan for the SLURM jobs of cluster.yaml, then submit them
kmhelpers plan coli_db -o coli_build/ --cluster cluster.yaml
bash coli_build/assets/initial/slurm/submit.sh

# Skip path validation (for exporting scripts)
kmhelpers plan coli_db -o coli_build/ --offline
```

## See Also

- [`apply`](apply.md) - run the plan
- [`build`](build.md) - run plan then apply in a single command
- [`compose`](compose.md) - generate index definition files
