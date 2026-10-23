# build

## Synopsis

Validate paths then build k-mer indices from an index definition file in a single command.

!!! abstract "USAGE"
    ```
    kmhelpers build [OPTIONS] INPUT
    ```

    | Argument | Description |
    |----------|-------------|
    | `INPUT` | The design directory (`DESIGN_DIR` of `design`), a compose directory or one of its indexes (`COMPOSE_DIR/NAME`), a session (`COMPOSE_DIR/NAME/SESSION` or its `index.yaml`), or one shard file (`SESSION/shards/<shard>.yaml`, built without merge) (required) |
    | `-s, --session SESSION` | Session to use when INPUT is a directory (default: the last one composed) |
    | `-o, --output-dir BUILD_DIR` | Index directory: receives the built index, reused across builds and passed to `query -r` (required) |

!!! abstract "I/O"
    **Input:** `DESIGN_DIR` of `design` (or `COMPOSE_DIR` of `compose`), with `-s` to pick a session; it resolves to `compose/NAME/SESSION/index.yaml` (see [design - Next Step](design.md#next-step))  
    **Output:** indices in `BUILD_DIR/<name>/`, registered in `BUILD_DIR/index.json`

## Advanced Options

| Option | Description |
|--------|-------------|
| `--bp, --base-path DIR` | Base path to resolve relative sample paths |
| `--threads INT` | Hidden. Force the number of kmtricks threads instead of sizing them from `--limits` |
| `--limits JSON` | Resource limits used to auto-size threads/partitions when `--threads` is not set (`ram`, `files`, `threads`), and the inputs of one merge (`ram`, `files`, `maps` = `vm.max_map_count`); see [build - Builds and merges](build.md#builds-and-merges) |
| `--safety-margin FLOAT` | Fraction of a detected system limit to use for any key missing from `--limits` (default: 0.9) |
| `--max-chunks INT` | Max number of kmtricks chunks a shard is built in; bigger chunks mean fewer build/merge passes but fewer threads. 0 disables the cap (default: 64) |
| `--cb, --chunk-budget INT` | K-mer budget of one kmtricks chunk: a chunk of span `s` holds at most `ceil8(budget / base^s)` samples. 0 for no limit (default: `2**37`), see [build - Shards and chunks](build.md#shards-and-chunks) |
| `--ncp, --skip-compression` | Skip compression of intermediate files during index building (useful on slow disks) |
| `--keep-previous` | Keep the replaced version of an updated index in `BUILD_DIR/work/SESSION/previous/` instead of deleting it |
| `--sp, --show-progress` | Enable animation that shows the current subindex being built (use in an interactive shell) |
| `--notify EMAIL` | Send email notification on exit (requires sendmail), with the log and the apply report attached |

## Paths

Two directories are involved, and they are distinct:

- `COMPOSE_DIR` holds the index definitions. It is the `-o` of `compose`, or `DESIGN_DIR/compose/` when using `design`.
- `BUILD_DIR` holds the built index. It is the `-o` of `build`, and the `-r` of `query`.

```
coli_db/                          DESIGN_DIR (design -o): INPUT of build
└── compose/                      COMPOSE_DIR
    └── coli/                     NAME: the index
        ├── layout.yaml           state of the index, shared by its sessions
        ├── initial/              SESSION (design/compose -s)
        │   ├── index.yaml        what INPUT resolves to (-s initial)
        │   └── shards/           one definition per shard (coli_g0_p0.yaml, ...)
        └── update/               the last session: built by default
            ├── index.yaml
            └── shards/

coli_build/                       BUILD_DIR (build -o, query -r): the kmindex registry
├── index.json                    registry of all built indices
├── coli_g0_p0/                   an index, in place (a directory, not a symlink)
├── coli_g1_p0/
├── work/                         only while a SESSION is being built
│   └── update/                   SESSION
│       ├── runs/                 kmtricks runs (parts, chunks)
│       ├── merges/               throwaway merge registries and their outputs
│       └── previous/             replaced version of an updated index
├── assets/
│   ├── initial/                  scripts (<shard>.sh, <shard>_merge.sh, kmhelpers_apply.sh) and fof files, one folder per SESSION
│   └── update/
└── logs/
    ├── kmhelpers_plan_<timestamp>.yaml    plan report, see Report below
    ├── kmhelpers_apply_<timestamp>.yaml   apply report
    └── coli_g0_p0_initial/kmtricks.log    one per kmtricks run built by apply
```

Reuse the same `BUILD_DIR` for every session of an index. Each index keeps one folder, `BUILD_DIR/<name>/`, for its whole life; a session only uses `BUILD_DIR/work/SESSION/` while it is built, and deletes it when it is done. Index names cannot be `work`, `assets`, `logs`, or start with `.`.

Building a session again resumes it: complete kmtricks runs are kept, incomplete ones are rebuilt, finished merges are not redone, and parts whose samples are already in their index are skipped. A finished session built again changes nothing. A run of `<shard>_merge.sh` interrupted at any point is finished by running it again (or `apply`): until the new version of a sub-index is registered, the sub-index is either registered with its previous folder or not registered at all, never registered with other data.

## Description

`build` chains [`plan`](plan.md) and [`apply`](apply.md) into a single invocation. It is equivalent to running the two commands in sequence.

**Step 1 - plan:** validates all sample paths upfront and writes the equivalent shell scripts to `BUILD_DIR/assets/SESSION/` (`<shard>.sh` and `<shard>_merge.sh` per sub-index, plus `kmhelpers_apply.sh` running them in order) and the plan [report](#report) to `BUILD_DIR/logs/`. Fix any path errors before the build starts rather than discovering them mid-run.

**Step 2 - apply:** executes the build, registers all completed indices in `BUILD_DIR/index.json`, and writes the apply [report](#report) as it goes.

**Filtering** - `build` always processes every shard of the session. Use [`plan`](plan.md) and [`apply`](apply.md) with `--shard` (names or glob patterns) or `--run` to build a subset.

**Notifications** - use `--notify` to receive an email when the build exits (requires `sendmail`). The notification is sent on both success and failure, including on `SIGTERM`, with the log file and the apply [report](#report) attached (the report so far, when the job was stopped).

### Shards and chunks

A shard is fixed at design: a span is split into shards of at most `ceil8(shard_budget / base^s)`
samples, see [compose - Sharding](compose.md#description). Each build then splits the new
samples of a shard into kmtricks runs (chunks), `<part>_chunk<N>`. A chunk holds the smallest of:

1. **Open files**: `files / threads - 1`, from `--limits files` (or the system limit x `--safety-margin`);
2. **Chunk budget**: `ceil8(chunk_budget / base^s)` samples (`--chunk-budget`, default `2**37`, 0 for no limit);
3. the samples of the part.

`--max-chunks` (default 64, 0 disables it) then raises the chunk to `ceil(samples / max_chunks)`,
so a shard is built in at most that many runs, with fewer threads to stay within the open
files. It never goes above bounds 1 and 2: when it would have to, `plan` warns and uses more
chunks. With the default budgets, a full shard fits 64 chunks (`2**43 = 64 x 2**37`).

### Builds and merges

Every sub-index is built as unregistered `kmtricks` runs, then published:

1. **Build** - each part of the sub-index (its samples of this session) is built with `kmtricks pipeline` into `BUILD_DIR/work/SESSION/runs/<part>/`, not registered. When one `kmtricks` build cannot hold all the samples of a part (open files, `--chunk-budget` and `--max-chunks`, see [Shards and chunks](#shards-and-chunks)), the part is built in chunks, `<part>_chunk<N>/`. These commands are in `assets/SESSION/<shard>.sh`, and can be run anywhere, e.g. as a SLURM array.
2. **Check** - `assets/SESSION/<shard>_merge.sh` starts by checking every run: `run_infos.txt` (written by kmtricks only when it finishes), `kmtricks.fof`, `options.txt`, and all partition matrices present, non-empty and of equal size. If one run is incomplete, the script stops before registering or merging anything; rebuild that run and run the merge script again.
3. **Publish a single run** - a new sub-index built in one run is moved in place (`kmindex register --mode move`): no copy, no merge.
4. **Merge** - otherwise the runs, plus the current version of the sub-index when it is already registered (see [Updating an index](#updating-an-index)), are merged. Each `kmindex merge` runs in a throwaway registry, `BUILD_DIR/work/SESSION/merges/<name>/<step>/`, holding only its inputs. `kmindex merge` loads the repartition table of every registered sub-index (2 MiB each at minimizer size 10), so a registry limited to the inputs keeps its memory proportional to what is merged. Merges get at most one thread per partition.
5. **Sub-shards** - one merge can take at most `k` inputs: `ram / (2 * 4^m)` (anonymous memory), `(maps - 1000) / threads` (`vm.max_map_count`) and `files / threads - 1` (open files), with the values of `--limits`. More inputs are merged in balanced groups of at most `k` (`<name>__sub1_<i>`), then these are merged, and so on. Each level reads and writes the data once more.
6. **Swap** - holding the lock `BUILD_DIR/.registry.lock` (several merge jobs may publish at once): the sub-index is unregistered, its current version is moved to `work/SESSION/previous/`, the merge result is moved to `BUILD_DIR/<name>/`, and registered. Queries see the previous version until the swap; during it (a second or so) the sub-index is not queryable. Moves are renames (an internal `kmhelpers manage move-dir`), so they take the same time whatever the size; they fail instead of copying if `work/` is on another filesystem.
7. **Check, then clean up** - `kmhelpers manage check --shard <name>` checks the published sub-index; only then are the runs, merges and previous version deleted. A failed check stops the script with everything kept.

`kmhelpers_apply.sh` runs `<shard>.sh` then `<shard>_merge.sh`. The plan logs, for each merge, its number of inputs, the limit that sets `k`, and its expected memory: the anonymous part must fit in RAM, while the mapped inputs are page cache that the kernel reclaims when they exceed it. The same merge plan is in the [report](#report), under `publish.steps`.

### Report

`plan` and `apply` each write a YAML report to `BUILD_DIR/logs/`: `kmhelpers_plan_<timestamp>_<n>.yaml` and `kmhelpers_apply_<timestamp>_<n>.yaml` (`build` writes both, without `_<n>`). Both have the same layout, organised by shard: `plan` fills in what will be built, `apply` adds what happened.

- `plan` writes its report once done; every run is `planned`.
- `apply` writes it after each part and each publish, with `summary.status: RUNNING` until the end: a running or killed apply leaves its report so far. The `--notify` mail attaches it.
- Each kmtricks run that `apply` runs writes `logs/<run>/kmtricks.log` (command, execution time, max CPU and memory, kmtricks output); the report reads its run metrics from there, also for a run reused from an earlier attempt.

??? example "An apply report (abridged)"
    ```yaml
    summary:
      command: apply
      status: SUCCESS
      input_type: index session
      started: '2026-10-19T20:39:57'
      finished: '2026-10-19T21:30:12'
      duration_s: 3015.2
      counts: {SUCCESS: 2, PARTIAL: 0, FAILED: 0, NONE: 0}
      totals: {shards: 2, samples: 169, runs: 2, est_size: 2.78GB, disk_size: 2.71GB}
      spans:
        169: {shards: 1, samples: 121, est_size: 1.44GB}
        178: {shards: 1, samples: 48, est_size: 1.33GB}
    input_file: .../compose/16SV4V5/initial/index.yaml
    build_dir: {path: .../16SV4V5, logs: .../16SV4V5/logs, assets: .../16SV4V5/assets/initial}
    kmindex: {version: 0.7.1, path: .../bin/kmindex}
    kmhelpers: {version: 0.8.0, path: .../bin/kmhelpers, git_commit: bcc3f5c}
    system:
      host: node58
      os: Linux
      kernel: 4.18.0-477.27.1.el8_8.x86_64
      cpus: 24
      slurm: {job_id: '179469', job_name: build_16SV4V5, partition: long, node: node58, cpus_per_task: '24'}
    limits:
      source: auto
      ram: 103.9GB
      ram_bytes: 103900000000
      files: 117964
      threads: 24
      max_map_count: 65530
      safety_margin: 0.9
      max_chunks: 64
      chunk_budget: 137438953472
    shards:
      16SV4V5_g0:                     # a shard
        result: SUCCESS
        16SV4V5_g0_initial:           # its part of this session
          result: SUCCESS
          span: 169
          samples: 121
          params:
            threads: 24
            partitions: 32
            partitions_source: auto
            minim_size: 10
            chunk_size: null
            kmer_size: 25
            abundance_min: 2
            bf_size: 31402272
            bitw: 3
            kmer_ratio: 448.62
          est_size: 1.44GB
          script: .../assets/initial/16SV4V5_g0.sh
          runs:
            16SV4V5_g0_initial:
              samples: 121
              action: built
              log: .../logs/16SV4V5_g0_initial/kmtricks.log
              duration_s: 1334.79
              max_cpu_pct: 2404.1
              return_code: 0
              started: '2026-10-19T20:39:58'
              finished: '2026-10-19T21:02:05'
              read_files: 242
              partitions: 32
              peak_rss: 20.09GB
              ram_limit_use: 0.193
              threads: 24
              cpu_efficiency: 1.0
        publish: {mode: move, duration_s: 4.1}
        disk_size: 1.40GB
        merge_script: .../assets/initial/16SV4V5_g0_merge.sh
      16SV4V5_g1:
        ...
    ```

| Field | Content |
|-------|---------|
| `summary` | `command` (`plan`, `dry-run`, `apply`), `status` (`SUCCESS`, `PARTIAL`, `FAILED`, `NONE`, or `RUNNING` while an apply goes on), times, result counts per shard, totals (shards, samples, kmtricks runs, estimated size, size on disk after an apply) and the same per span |
| `kmhelpers` | version, path, and `git_commit` when the environment variable `GIT_COMMIT` is set |
| `system` | host, kernel, CPUs, and `slurm` (job id, array task, name, partition, node, CPUs, memory) when run in a SLURM job |
| `limits` | what threads, partitions, chunks and merges were sized with: `source` (`auto`, `--limits`, `--threads`), RAM, open files, threads, `vm.max_map_count`, `--safety-margin`, `--max-chunks`, `--chunk-budget` |
| `shards.<shard>` | `result`, its parts, and how it is published: `publish.mode` (`move` a single new run, `merge`, or `register` a folder left by an interrupted publish), `absorbed`, `updates` (the shard was already built), the merge `threads`, `max_inputs` and `bound_by`, `steps` (each merge, its inputs and its expected anonymous and mapped memory, `est_anon`, `est_mapped`); after an apply, `publish.duration_s` and `disk_size` |
| `shards.<shard>.<part>` | `result`, `span`, `samples` (`planned_samples` if some were skipped), `issues`, `error`, `params` (threads, partitions and `partitions_source`, minimizer size, chunk size, k-mer size, abundance min, Bloom filter size, `bitw`, k-mer ratio), `est_size`, `script` |
| `...<part>.runs.<run>` | one per kmtricks run (the part, or its chunks): `samples`, `action` (`planned`, `built`, `rebuilt` an incomplete run, `reused` a complete one), and from its `kmtricks.log`: `duration_s`, `started`, `finished`, `peak_rss` (reported by kmtricks, else sampled), `max_cpu_pct`, `cpu_efficiency` (`max_cpu_pct / (100 x threads)`), `ram_limit_use` (`peak_rss / limits.ram`), `read_files`, `partitions`, `return_code` |

`partitions_source` tells where the partition count comes from: `design` (`compose -P`), `auto` (sized from the limits for a full shard), `registered` (the shard is already built with another count) or `run` (a run of the session was already started with another count). The last two override the planned count, since only indexes with the same count can be merged.

**Reading it**

- **A slow run**: a `cpu_efficiency` well below 1 means kmtricks waits on its inputs (slow storage, or a node with a bad mount or network). Compare `duration_s` and `system.host` with other runs of similar size.
- **Memory headroom**: `ram_limit_use` is the share of the RAM limit the run used at its peak. Close to 1, lower `--safety-margin` or `--limits ram`; far below it on every run, the limit can be raised for more threads.
- **A killed job**: a report still `RUNNING` after the job ended was cut off; it lists the parts and runs done so far. Run `apply` again: complete runs are `reused`.
- **Builds run by the scripts**: the exported `.sh` scripts run kmtricks without writing `kmtricks.log`, so their runs have no metrics, also when a later `apply` reuses them.

To record the kmhelpers commit in the report, set `GIT_COMMIT`, e.g. in a SLURM script:

```bash
export GIT_COMMIT=$(git -C /path/to/kmhelpers rev-parse --short HEAD)
kmhelpers apply coli_db -o coli_build/
```

### Updating an index

Building a new `SESSION` into a `BUILD_DIR` that already holds the same index adds the new samples to it. `kmindex` cannot add samples to an existing index in place, so an update merges the current version and the new runs into a **new** index:

- The updated index `NAME_gN` replaces the previous one in `BUILD_DIR/NAME_gN/`. It keeps its name and its folder, so queries need no change.
- The previous version is deleted once the updated one is registered and checked. Use `--keep-previous` to keep it in `BUILD_DIR/work/SESSION/previous/NAME_gN/` instead, e.g. to compare both versions; delete that folder once done.
- Only the sub-indices that receive new samples are merged. The others are untouched.
- A sample can only be added once: a part whose samples are all already in the index is skipped, and a part where only some are fails.

!!! warning "Disk space"
    Both versions coexist on disk during the merge. Plan for at least twice the size of the sub-indices being updated.

Indices built by older versions of kmhelpers (registered as symlinks to `BUILD_DIR/kmindex_data/SESSION/NAME_gN/`) keep working. Updating one moves it in place, and deletes its previous version in `kmindex_data/`.

## Examples

```bash
# Build the index defined by design/compose in session "initial"
kmhelpers build coli_db -o coli_build/

# Add an update session to the same index directory
kmhelpers build coli_db -s update -o coli_build/

# Set threads and show progress
kmhelpers build coli_db -o coli_build/ --limits '{"threads": 8}' --sp

# Notify by email when done
kmhelpers build coli_db -o coli_build/ --notify user@example.com
```

## See Also

- [`plan`](plan.md) - plan step only
- [`apply`](apply.md) - apply step only
- [`design`](design.md) - design the index before building
- [`query`](query.md) - query the index in `BUILD_DIR`
