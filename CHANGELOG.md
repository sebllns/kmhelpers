# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added

- **`plan --cluster FILE`**: a YAML file (`type: slurm`) of the partition, time, excluded nodes, setup lines and the resources of each kind of job (`jobs.build`, `jobs.publish`, `jobs.check`); the plan is sized from these resources (`--limits` with `--cluster` is refused), and `BUILD_DIR/assets/SESSION/slurm/` gets `build.sbatch` (an array task per build job), `publish.sbatch`, `check.sbatch` and `submit.sh`
  - `submit.sh` submits what `apply --pending` lists: the build array (`max_parallel`, split at `MaxArraySize`), each publish job after the array tasks of its own shard, then `manage check` after everything; safe to run again
- **`plan --chunks-per-job N`**: the chunks of a shard are split into jobs `<shard>_j<k>` of up to N chunks, then a job `<shard>_publish`; 0 (default) keeps one job per shard
- **`build --hpc FILE`** (`--cluster`): plans for the jobs of the cluster file, runs the generated `submit.sh` and exits; nothing is submitted for a `FAILED` or `PARTIAL` plan
- **Progress**: `apply` records each step in `assets/SESSION/<shard>/state/<step>.json` and rewrites `assets/SESSION/progress.yaml` after each one; **`apply --status`** prints it per shard and step: `SUCCESS`, `FAILED` (log and error), `CANCELLED` (SIGTERM), `RUNNING` (job, node, start), `LOST` (running job gone from `squeue`), `PENDING` (with its SLURM job once submitted)
- **`--show-progress` / `--sp`** (`apply`, `build`): one line per started shard, a progress bar of its steps (chunks and publish), its time, the steps running (how many, and the 3 oldest with their time) and a colored end status (SUCCESS, FAILED with step and log, LOST, CANCELLED); redrawn in a terminal, printed at each step end otherwise. `apply --status --sp` (and `build --hpc --sp`) follows a cluster build every `--interval` seconds until it ends, exiting 0 on SUCCESS
- **`apply --status --task PATTERN`** (and `--status --sp --task`, `apply --sp --task`): only the matching shards and steps, in detail: job and node, time, RAM of a running step (`sstat` MaxRSS against the job's `--mem` on SLURM, psutil against the plan's RAM limit for a local `apply`; colored at 80 % and 95 %) and its current kmtricks phase (`Count partitions 63%`, read from the tail of its log); live, one line per running step under its shard. The global status is unchanged
- The logs of the steps of `apply` are written as the step runs (stdout first, then stderr and the resource usage, under `--- RESOURCES ---`, at the end), so a running step can be followed
- **`--notify-level global|shard`** (`apply`, `build`): `shard` also mails each shard when it ends; the mails carry the progress tree. On a cluster, the jobs ending a shard send the shard mails and the finish job the final one
- SLURM files: a **finish** job replaces the check job, after every job (`afterany`): checks the registry when all is built, writes `progress.yaml`, mails it with `build --notify`; publish and finish jobs get `--kill-on-invalid-dep=yes`, so a failure never leaves jobs pending; `submit.sh` records submissions in `slurm/submitted.tsv` and never submits again a job still queued or running
- **`design --redesign`**: removes the previous design of the index (`compose/NAME/`, `profile/`) and designs it again; without it, `design` warns when it reuses an existing layout (an update: groups and shards kept, `-g`, `-b`, `--sb`, `--ab` not used)
- `design` / `compose` refuse a session already in the layout: its samples were counted twice
- **Published partition count in the layout**: `apply` records the partition count of each shard it publishes (or finds published) under the shard, `map.<span>.shards[].partition_count`, under a lock and only when missing; `compose` writes the layout under the same lock, keeps the counts recorded while it ran and across sessions and later `plan`s use it (`partitions_source: published`). A `-P` given later applies to new shards only
- **Lock files removed once the build is done**: the finish job, after a passed `manage check`, runs `apply --cleanup` (hidden), which removes `BUILD_DIR/.registry.lock` and `layout.yaml.lock` unless another process holds them; a local `apply`/`build` of the whole plan does the same when it completes it. Every kmhelpers lock is a `flock(2)` lock, the one the publish scripts take
- **A session is planned once**: `build` on a session that already has a plan runs it (resumes it, or submits what is not done with `--hpc`; `NOTHING TO DO` when everything is built) instead of planning again, warning about the options it does not use; `plan` refuses it. **`--replan`** (`plan`, `build`) removes `BUILD_DIR/assets/SESSION/` and plans again (indexes, built runs and logs stay)
- While jobs of the current plan are still queued (`squeue`) or running (a local `apply`), `build` follows them (as `apply --status --sp`, or prints their status once outside a terminal) instead of planning again, and `plan` refuses: planning rewrites the scripts and states under them; `submit.sh` keeps a finish job still pending when it submits nothing new, and replaces it otherwise (one final mail)
- **One group for small indexes**: `-g 0` keeps one group when one group takes at most a size, whatever a 2nd one would save in proportion: `design` uses 4 GB of built index (4 GB / bitw of profile size), `profile` no size by default (`--auto-group-single-max SIZE`, env `KMHELPERS_AUTO_GROUP_SINGLE_MAX`, `0` turns it off); recorded as `single_max` and `single_size` under `auto_group` in `profile.yaml`
- **`profile`/`design --no-grouping, --ngp`**: one group, no grouping strategy (`grouping: none` in `profile.yaml`); refused with `-g N`
- `profile.md`: the sizes of `profile.yaml` are for presence/absence, times bitw for an abundance index
- **`apply --task PATTERN`** runs part of the plan: a shard or its task (`<shard>_<session>`) runs all its jobs, a job (`<shard>_j<k>`, `<shard>_publish`) runs alone; **`apply --pending`** lists the jobs not done yet

### Changed

- Auto-sized partition counts (`plan`, no `-P` and no published count) are rounded up to the next power of 2, at most 256; a count fixed by `-P` or recorded for a published shard is kept as is
- **`plan` prepares, `apply` runs**: `plan` takes every build decision and writes `BUILD_DIR/assets/SESSION/plan.yaml` (one task per part: its chunks, publish step and jobs) and one directory of scripts per shard, `<shard>/` (`<run>.sh` and `.fof` per kmtricks run, `publish.sh`, `publish/`); `apply` runs these scripts, under monitoring, and builds nothing itself
  - `apply` refuses a missing plan, and a stale one: an input changed since (definition, shard files, `layout.yaml`, sample lists, cluster file, hashed in `plan.yaml`) or another kmhelpers version made it
  - `apply --shard` is replaced by `apply --task`
  - `apply` has no sizing option any more (`--limits`, `--safety-margin`, `--max-chunks`, `--chunk-budget`, `--threads`, `--base-path`, `--skip-compression`, `--keep-previous`): they are options of `plan` (and `build`)
  - Before publishing a shard, `apply` checks the registry is as `plan` saw it (`expects`), or as an interrupted run of the same publish step leaves it
  - Each run script skips samples already published and complete runs, and deletes and rebuilds an incomplete run, so every script can be run again
  - Logs per shard: `BUILD_DIR/logs/<shard>/<run>.log` and `publish.log`
- The plan/apply report records `kmhelpers.commit`, the git commit of the installed kmhelpers (`UNKNOWN` outside git), instead of `git_commit` from `$GIT_COMMIT`, which is no longer read
- Docs: `commands/index.md` lists every environment variable, and explains the configuration file (`-C`) and the precedence of command line, environment, configuration file and defaults
- The command duration (`Done in ...`) is printed to stderr, so stdout carries only a command's output (e.g. `apply --pending`)

- **Open-files limit**: chunks and merges are sized from the hard limit (`ulimit -Hn`) instead of the soft one, so a low soft limit no longer cuts needless chunks
  - Every command raises the soft limit to the hard one at start (logged with `-V`, a warning if it fails), inherited by kmtricks, kmindex and the merge steps
  - The scripts in `BUILD_DIR/assets/SESSION/` raise it too (`ulimit -Sn "$(ulimit -Hn)"`), when run by hand or in a SLURM job
  - The plan/apply report records `files_soft` and `files_hard` under `limits`

### Removed

- `plan`/`apply --run`: replaced by jobs (`plan --chunks-per-job`, `apply --task`)
- `BUILD_DIR/assets/SESSION/kmhelpers_apply.sh` and the flat `<shard>.sh` / `<shard>_merge.sh` scripts: replaced by the per-shard directories
- Support for build directories of older kmhelpers: parts registered on their own (merged in as they were), and symlinked index folders

## [0.8.0] - 2026-10-19

### Added

- **k-mer ratio**: `list` records `kmer_total` (k-mer occurrences, ntcard F1) next to `kmer_count`; `compose` records each shard's `kmer_ratio` (largest `kmer_total / kmer_count` of its samples, else 1 assembled / 4 raw reads, times `compose`/`design --kr, --kmer-ratio`) in `index.yaml` and the shard files, and `plan` sizes partitions and threads from the Bloom filter capacity × that ratio, since kmtricks holds every occurrence before `--hard-min`
- **`compose`/`design --ncl, --no-copy-list`**: the session points to the input sample list instead of copying it to `SESSION/samples.jsonl`; `design` never copies the list it writes (`list/samples_<SESSION>.jsonl`), so its sessions have no `samples.jsonl`
- **Automatic group count** (`profile -g 0`, `design -g 0`): starts from one group per 1000 samples, then adds one while it saves at least 20% of the storage, up to 20 groups
  - Tuned with `profile --auto-group-samples`, `--auto-group-max` and `--auto-group-min-gain` (env: `KMHELPERS_AUTO_GROUP_*`), recorded under `auto_group` in `profile.yaml`; `design` reads only the environment variables
- **Abundance indexes**: `design --ab N` / `compose --ab N` (`--abundance-bits`) compose an index storing `N` bits per sample and k-mer (2^N abundance classes), built by kmtricks with `--mode hash:bfc:bin --bitw N`
  - `bitw` is stored in the index definitions and the layout; definitions without it, and `--ab 0` (default), are presence/absence as before
  - An update with another `bitw` than the layout is refused: presence/absence and abundance indexes cannot be merged
  - Storage estimates, shard sample limits, merge memory and `bytes_per_row` count `bitw` bits per sample
  - Queries report the abundance class of each sample instead of the fraction of k-mers found
- **`list --paired [REGEX]`** (`design --paired`): groups mate files (R1/R2) of a directory into one sample
  - The default regex matches mate tokens such as `_R1`, `_R2`, `_1`, `.2`; `--paired=REGEX` sets a custom one
  - Without `--paired`, a warning is logged when unassembled files (`--dt u`) look like read pairs
- **`query --export` (`-x`)**: writes a Markdown or HTML report beside the data results
- **`query -f none`**: keeps only the raw kmindex results
- **Query statistics**: `sequence_stats.tsv` (one row per query sequence) and `sample_stats.tsv` (one row per matched sample), with match count, perfect matches and mean and median scores; `--no-stats` skips them. The overall rows are also in the md and html reports
- **Plan/apply report** (`BUILD_DIR/logs/kmhelpers_{plan,apply}_*.yaml`): organised by shard (`run` renamed `shards`, the span table moved to `summary.spans`), with a `summary` (status, times, counts, totals), the host, kernel, CPUs and SLURM job, the resolved limits, `kmhelpers.git_commit` from `$GIT_COMMIT`, each part's build parameters (with `partitions_source`: `design`, `auto`, `registered` or `run`), scripts and kmtricks runs, and how each shard is published (merge steps and their estimated memory)
  - `apply` adds per run the duration, peak RSS, max CPU, CPU efficiency and share of the RAM limit read from `logs/<run>/kmtricks.log`, and per shard the publish duration and size on disk
  - Written as the run goes: a running or killed `apply` leaves its report so far (`summary.status: RUNNING`), also attached to the `--notify` mail
- **`--keep-previous`** (`plan`, `apply`, `build`): keeps the replaced version of an updated index in `BUILD_DIR/work/SESSION/previous/`
- **`manage check -n`**: checks only the given indices, and fails if one is not registered
- **`manage move-dir`** (internal, hidden): renames a folder for the generated scripts, failing instead of copying across filesystems
- **`manage remove --missing-ok`** and **`--keep-link`**: skip unregistered IDs; only edit `index.json`
- **Shard budget** (from Logan, `compose`/`design --sb, --shard-budget`): a shard of span `s` holds at most `ceil8(budget / base^s)` samples
  - Defaults to `2**43` for a new index; `--shard-budget 0` disables it
  - `shard_budget` is stored in the layout; an update keeps it, passing it again re-shards the layout
- **Chunk budget** (`plan`, `apply`, `build` `--cb, --chunk-budget`): a kmtricks chunk of span `s` holds at most `ceil8(budget / base^s)` samples (default `2**37`, 0 for no limit), still within the open-files limit and `--max-chunks`

### Changed

- **Option names made consistent**
  - `design`/`compose -s, --session` (was `--session-id`), the same name as in `plan`/`apply`/`build`
  - `design -a, --autorename` (was `-r`), as in `list`
  - `design -p, --paired`, as in `list`; `design`/`compose -P, --partition-count` (was `-p`)
  - Shards are selected with `--sh, --shard` in `plan`, `apply`, `query`, `manage` and `compress` (was `-n, --name`, `--index-ids`, `--index-id` or `--index-name`); `-n, --name` is only the index name of `design`/`compose`. `query --shard` also takes comma-separated names
  - `plan`/`apply`/`build --bp, --base-path` and `query --bq, --batch-query` (were `-b`); `-b` is `--base` in `profile`/`design`
- **Minimizer size is set at design**: `design`/`compose --minim-size` (default 10, an update takes the layout's value and refuses another one); `plan`/`apply`/`build` lose `--minim-size`
- **Partition count**: `-p` only on `design`/`compose`, where it fixes the count of every shard for the life of the index; otherwise `plan`/`apply`/`build` choose it per shard: a built shard keeps its count (another value is ignored with a warning), then started runs of the session, then the design's `-p`, else the resource limits. `plan`/`apply`/`build` lose `-p` and no longer write the design's layout
- **Compose output**, simpler to read; old layouts and definition files are no longer read
  - Everything about an index is in `COMPOSE_DIR/NAME/`: its layout is `NAME/layout.yaml` (was `COMPOSE_DIR/NAME_layout.yaml`), which also records the sessions composed
  - A session `NAME/SESSION/` holds `index.yaml` (replacing the span registry `NAME.yaml`): parameters, size and shards of the session, keyed by shard name
  - Each shard's definition is in `SESSION/shards/<shard>.yaml` (was `SESSION/<shard>_<SESSION>.yaml` next to the entry file)
  - File names lose the `NAME_` prefix: `samples.jsonl`, `summary.csv` (one row per shard); `orig_dist.csv` is replaced by `distribution` in `index.yaml`
  - `design` writes its sample list to `DESIGN_DIR/list/samples_SESSION.jsonl`
- **`plan`, `apply`, `build` take a directory**: the design directory, a compose directory or `COMPOSE_DIR/NAME`, resolved to the session given by the new `-S/--session` or the last one composed; a session's `index.yaml` or a shard file can still be passed
- **`compose`/`design --ab`** defaults to the layout's value on an update (0 for a new index), instead of 0; an explicit different value is still refused
- **Default group count** (`profile -g`, `design -g`): 0 (automatic) instead of 20
- **New indexes are sharded by default** under the shard budget: shards are named `NAME_g<i>_p<k>` (was `NAME_g<i>` without `--shard-size`); layouts without a budget keep no limit
- **`compose`/`design --shard-size` (`-si`) is now the hidden `--shard-budget-bytes`**: it caps a shard by bytes on disk instead of the shard budget, not on top of it, and cannot be combined with `--shard-budget`
- **`--max-chunks`** (`plan`, `apply`, `build`): caps the chunks of a shard, default 64 (was 200)
- **Multi-letter short flags take two dashes**: `-dt`, `-lg`, `-ntt`, `-nc`, `-fp`, `-ab`, `-pf`, `-pr`, `-NC`, `-SP`, `-NF` (and `test` `-mu`, `-sd`) become `--dt`, `--lg`, `--ntt`, `--nc`, `--fp`, `--ab`, `--pf`, `--pr`, `--ncp`, `--sp`, `--NF` (`--mu`, `--sd`); single-letter flags keep one dash
- **Option case: uppercase short flags only for global options**; long names are unchanged
  - Global: `-v`, `-q`, `-y` become `-V`, `-Q`, `-Y` (`-C`, `-L`, `--NF` unchanged)
  - `compose`/`design`/`plan`/`apply`/`build`: `-S` becomes `-s` (`--session`); `plan`/`apply`: `-X` becomes `-x` (`--fail-fast`); `apply`/`build`: `--SP` becomes `--sp`; `plan`/`apply`/`build`: `--NC` becomes `--ncp` (`--skip-compression`); `plan`: `-O` becomes `--off` (`--offline`)
  - `query`: `-R` becomes `--thr` (`--threshold`), `-T` becomes `--tms` (`--timestamp`), `-K` becomes `--kpq` (`--keep-query`), `-P` becomes `--par` (`--parallel`), and `--vec` loses `-V`
  - The hidden `compose`/`design -P, --partition-count` keeps its capital: `-p` is `--pair-regex` in `design`
- **`-H, --HELP`** on every command: the help including hidden options, marked `[hidden]`
- **`--threads`** (`plan`, `apply`, `build`) is hidden and loses `-t`: threads are sized from `--limits` (e.g. `--limits '{"threads": 8}'`)
- **Shard selection by glob pattern**: `plan`, `apply`, `query` and `compress` `--sh, --shard` take glob patterns (`'idx_g0_*'`); a name without wildcard matches exactly. A pattern matching nothing is a warning; only no match at all is an error (also for `--run`). `plan`/`apply -s, --span` is removed: `--shard 'NAME_g<i>*'` selects a group
- **`compress` without `--shard` compresses every shard of the registry**, one after the other; a failed shard does not stop the others, the command fails at the end
- **`plan`/`apply --run PATTERN`**: builds only the matching kmtricks runs (`<part>`, `<part>_chunk<N>`) without merging, e.g. one chunk per SLURM array task; a later `apply --shard` merges them
- **`design`/`compose -P, --partition-count`** is hidden: the partition count is sized at plan from `--limits` unless fixed
- **`KmtricksWrapper.pipeline`, `KmindexWrapper.build`**: `bloom_size` is required and `bitw` optional; with `bitw` set, the index is an abundance index of `bloom_size` cells, otherwise presence/absence (`nb_cell` removed)
  - Its size estimate counts `bloom_size` in bits (it was read as bytes)
- **Index layout**: every index lives in place in `BUILD_DIR/<name>/` (a directory of the registry, not a symlink), and keeps that folder across updates
  - Everything temporary to a session (kmtricks runs, merges, previous version) is in `BUILD_DIR/work/SESSION/`, deleted when the session is done; `BUILD_DIR/kmindex_data/` is no longer used
  - `plan`, `apply` and `build` derive every path from one place (`BuildPaths`); scripts always go to `BUILD_DIR/assets/SESSION/`
  - Indices of older build dirs (symlinks to `kmindex_data/SESSION/`) keep working; updating one moves it in place
- **Session parts** are built like chunks: unregistered `kmtricks pipeline` runs, checked, then published by the merge script
  - A new index built in one run is moved in place (`kmindex register --mode move`) instead of being copied by a 1-input `kmindex merge`
  - An update merges the current version with the new runs in a throwaway registry, then swaps them under a lock (`BUILD_DIR/.registry.lock`): unregister, current version aside, new version in place, register
  - An interrupted merge script is finished by running it again: merge steps leave a `done` marker, moves are skipped once made, and the plan reads an index's samples from its folder (`kmtricks.fof`), so an index left unregistered mid-swap is recognized
  - The published index is checked (`manage check -n`) before its inputs are deleted
  - The previous version is deleted once the updated one is checked (it was left in `kmindex_data/` for manual deletion)
  - `plan` no longer renames anything in `index.json` (it renamed the updated index to `<name>_prev_<timestamp>`)
- **Resuming a session**: building a session again keeps complete runs, rebuilds incomplete ones and skips parts already merged into their index; `build` no longer refuses an existing session folder
- **Chunked builds**: chunks are built with `kmtricks pipeline` and stay unregistered until they are merged
  - The merges go to their own script, `<shard>_merge.sh`, run after the builds (e.g. after a SLURM build array)
  - The merge script first checks every chunk (`run_infos.txt`, all partition matrices present and of equal size) and stops before registering anything if one is incomplete
  - Each merge runs in a throwaway registry holding only its inputs, so its memory no longer grows with the number of sub-indices registered in the main registry
  - When a shard has more chunks than one merge can take (anonymous RAM, `vm.max_map_count`, open files), they are merged in balanced groups (sub-shards), then the sub-shards are merged
  - The merged shard is then registered in the main registry; chunks, intermediate merges and throwaway registries are deleted
- **Merge threads**: `kmindex merge` gets at most one thread per partition (it runs one task per partition)
- **`--limits`**: new optional `maps` key (default: `vm.max_map_count` of the machine)
- **`query -f`**: selects the data format only (`tsv`, `json`, `yaml`, `none`); `-f md` and `-f html` are deprecated and map to `-f tsv --export md|html`. `--print` prints the data only
- **Query module**: split into `pipeline/query.py` (runner), `pipeline/query_result.py` (`KmindexQueryResult`, still importable from `pykmhelpers`) and `pipeline/query_report.py`
- **Documentation**:
  - New [Python API](https://sebllns.github.io/kmhelpers/latest/tutorials/ecoli_api/) tutorial reproducing the *E. coli* tutorial, with per-step options, and an advanced page (custom sample lists and JSONL, filtering between steps, script-based builds, streaming and merging query results); script in `examples/tuto_ecoli_api.py`
  - The *E. coli* tutorials and `examples/tuto_ecoli_e2e.sh` scan the dataset directories instead of using file lists
  - `list`: new "When to use a sample list" section
  - New `sample_lister` API reference page

### Removed

- **`cli/kmindex.py`**: the `kmhelpers kmindex` group, no longer registered; and the unused diagram sources `docs/diagrams/pipeline_diagram_v1.drawio`, `pipeline_diagram_v2.drawio`
- **`compose` docs** of options removed earlier (`--partition-min-size`, `--partition-count-limit`, `--split-size`)
- **`-r/--registry` and `-bl/--bloom-dir`** (`plan`, `apply`): the registry is `BUILD_DIR`, where indices live in place
- **`--on-conflict`** (`plan`, `apply`): builds are never registered, an existing run is kept when complete and rebuilt otherwise

### Fixed

- **`compose` hard min**: the `abundance_min` of the JSONL header (2 for unassembled data) is used, instead of always 1
- **Python 3.11**: deleting an index used `shutil.rmtree(onexc=...)`, which exists only from Python 3.12
- **`manage remove`**: always deleted the index files, ignoring `-d/--delete-files`
- **`query`**: results were lost when kmindex wrote one file per batch (`batch_N/`), and a query without match was reported as failed
- **`examples/pipeline_api.py`**: used `IndexOpsConfig` arguments removed by the in-place index layout

## [0.7.1] - 2026-10-07

### Added

- **Compressed query inputs**: `query` accepts gz, bz2, xz and zst FASTA/FASTQ files, including from stdin
- **`query --keep-query` (`-K`)**: Copies the query file into its output directory
- **`about`**: Shows the commit subject, the documentation URL and third-party tool links

### Changed

- **`query`**: Query files are no longer copied into the output directory by default (use `--keep-query`)

### Fixed

- **Packaging**: The `pykmhelpers.pipeline.index_ops` subpackage was missing from the wheel and sdist, so `kmhelpers` failed at import after `pip install`
- **`query`**: `info.yaml` is written when a query fails, with the error and the kmindex output

## [0.7.0] - 2026-09-30

### Added

- **`install-deps` Command**: Download `kmtricks`, `kmindex` and `ntcard` binaries
  - `ntcard` comes from the portable builds of the `sebllns/ntCard` fork, verified against the release `SHA256SUMS`
  - `--ntcard VERSION` selects the release, `0` skips it

- **`check-deps` Command**: Verify that `kmindex`, `kmtricks` and `ntcard` are available

- **`test auto-params` Subcommand**: Print the build parameters chosen from the hardware limits, without running a build

- **Index sharding**: `compose` / `design` `--shard-size` splits a span into independent shards that are never merged together
  - The per-span sample limit is derived from the Bloom filter size
  - Updates fill the last shard, then open a new one

- **Resource limits for builds**: `--limits`, `--safety-margin` and `--max-chunks` on `build`, `plan` and `apply`
  - `--max-chunks` caps the number of build chunks (default 200, `0` disables), trading threads for fewer build/merge passes
  - Resource detection works on SLURM nodes (`core/resources.py`, formerly `core/system.py`)

- **Per-group build scripts**: `plan` and `build` export one script per group of parts (build, merge into the target, cleanup of merged data)
  - `build` writes scripts and fof/param files to `assets/<session>/`, `assets/kmhelpers_apply.sh` runs the last session
  - Scripts use `set -euo pipefail` and print timestamped step logs

- **Compressed samples**: `list` detects compressed data extensions and supports `.zst` decompression

- **Query run metadata**: HTML and Markdown query reports include the command, execution time, max CPU and max memory

- **Examples**: `examples/mini_e2e.sh` (random-data end-to-end run) and a large-scale offline planning example

- **Documentation**: k-mer counting, index definition, and groups/partitions tuning pages; kmtricks parameter formulas (`vendor/kmparams_formulas.md`)

- **CI**: `ntcard-binaries` workflow for portable `ntcard` builds (since moved to the `sebllns/ntCard` fork)

### Changed

- **Breaking**: `apply` option `--existing` renamed to `--on-conflict`, as in `plan`
- **Breaking**: `--from` removed from `plan` and `apply`
- **Breaking**: `compose` / `design` partitioning options (`--split-size`, `--partition-min-size`, `--partition-count-limit`) replaced by `--shard-size`
- **Breaking**: `build-subindex` command removed
- **Breaking**: `list` stores imported sample paths relative to `root_path`
- **Layout**: Stores the partition count, minimizer size, shard size and per-span sample counts; `compose -p` fixes the partition count, otherwise the first build sizes it; the `_p<n>` suffix is dropped when sharding is off
- **Build parameters**: The kmtricks minimum partition count is applied; `auto_params` checks its bounds; with a fixed partition count, threads absorb the RAM limit
- **Merge naming**: A part is named after the index it is merged into; chunk name lists are collapsed in logs and scripts
- **`index_ops`**: Split into a package of single-purpose components; build parameters are resolved once per index
- **Logging**: `test` commands use the logger instead of `print`

### Fixed

- `plan` passing `--minim-size None` to kmindex (defaults to 10)
- Partition count and minimizer size per index in the layout
- `pipeline_api` example after the composer option removal
- E. coli end-to-end tutorial script

### Known issues

- `test auto-params`: the estimated index size display is inconsistent and has been removed from the output
## [0.6.4] - 2026-09-30

### Added

- **`manage info`**: Shows the resolved data path of the index and the estimated on-disk size of its Bloom filter matrices (`path` and `estimated_data_size` in JSON output)
- **`design`**: Logs the suggested `build` command once the index definition is written
- **Bioconda recipe**: `recipe/meta.yaml` rewritten for a bioconda submission (tagged tarball source, `noarch: python`, full runtime dependencies)
- **E. coli end-to-end script**: `examples/tuto_ecoli_e2e.sh` runs the tutorial from download to query
- **Index update tutorial**: Dedicated page (`docs/tutorials/ecoli_update.md`) covering the merge, the disk cost, and the old/new index paths
- **ntCard binaries workflow**: Manually triggered GitHub Actions workflow building `ntcard` binaries

### Changed

- **Help messages**: `design`, `compose`, `plan`, `build`, and `apply` now use consistent directory names (`DESIGN_DIR`, `COMPOSE_DIR/NAME/SESSION/`, `BUILD_DIR`) and example paths from the E. coli tutorial
- **Documentation**: Clarified paths for `compose`, `plan`, `build`, and `apply`, the `design` output and its handoff to `build`; query pages reflect TSV as the default output format
- **Docs deployment**: Push to `docs` publishes a preview, production deploy is triggered manually
- **kmindex**: The bioconda release of `kmindex` (>= 0.6.1) supports `static_repart`; building from source with `scripts/setup.sh` is no longer required

### Fixed

- Installed package missing `pykmhelpers.vendor`, which broke `build_params` imports outside a source checkout
- `profile`: Number of groups capped at the number of spans
- `manage info`: Size estimate for indices with an unresolved partition count
- `examples/pipeline_cli.sh`: Query results read from `kmindex_output/` and a missing result fails explicitly
- Paper DOIs

## [0.6.3] - 2026-08-04

### Added

- **`profile` Command**: Analyse a JSONL sample list and produce a Bloom-filter span profile
  - Assigns each sample to a span bucket based on its k-mer count
  - Outputs `profile.yaml` and a span distribution plot
  - Supports configurable base, false-positive rate, and span grouping

- **`plan` Command**: Dry-run with upfront path validation before building
  - Validates all sample paths and reports missing files
  - Writes a ready-to-execute shell script without running it
  - Replaces the `--plan` / `--dry-run` flags previously embedded in `apply`

- **`pipeline` Command**: Run a full sequence of commands from a YAML definition file

- **`about` Command**: Display version info and ASCII banner

- **`test create-list` Subcommand**: Generate a fake JSONL sample list, as produced by `list`
  - K-mer counts drawn from a lognormal distribution (median count, standard deviation expressed in spans)
  - Configurable sample count, k-mer size, name prefix, data type, root path, and seed
  - Useful to exercise `profile` and `plan` without real data

- **`query --vec` / `-V`**: Export the per-k-mer presence/absence vector `P` in addition to the coverage ratio `R`
  - Vectors are run-length encoded in the reports to keep them compact
  - Adds coverage output: a coverage track in HTML, a `coverage.tsv` beside `results.tsv`

- **Automatic build parameters from hardware limits**: Build steps derive their parameters from the available memory and CPU (`core/build_params.py`, vendored `kmparams`)

- **`KMHELPERS_SEED` Environment Variable**: Seed the random generator for reproducible test data

- **Examples**: `examples/pipeline_cli.sh` and `examples/pipeline_api.py` walking through the full pipeline from the CLI and from the Python API

- **Dynamic commit reporting**: The build commit is resolved at runtime instead of being frozen at release time (`scripts/collect_versions.sh` replaces `scripts/freeze_commit.py`)

- **GitHub issue forms**: Templates for bug reports, feature requests, and documentation issues

- **JOSS paper**: Paper sources and figures under `paper/`, built only on the `paper` branch

- **`scripts/setup.sh`**: Automated build script for `kmindex` and `kmtricks` from source
  - Required for 0.6.3, `static_repart` index type is not yet in the conda release of `kmindex`

- **MkDocs documentation site**: Complete documentation with tutorials, command reference, and contributing guide
  - End-to-end E. coli tutorial with a metro-map pipeline diagram

- **`IndexComposer`** (`pipeline/composer.py`): Core class that composes samples into Bloom-filter spans; index fingerprint renamed to *layout*

- **`QueryRunner`** (`pipeline/query.py`): Query pipeline logic extracted from the CLI into a dedicated class

- **GitHub Actions release workflow**: Builds sdist and wheel for PyPI packaging

- **GitHub Actions docs workflow**: Versioned documentation deploy via `mike` on push to `docs`

- **CI compile guard**: `compileall` matrix (Python 3.8-3.11) to catch version-specific syntax early

### Changed

- **`list`**: Input now accepts a directory, a plain-text file, or a YAML file (auto-detected); output format changed from YAML to JSONL; plain-text format supports optional sample ID and k-mer count per line; continuing after an error is now opt-in with `-c` instead of automatic
- **`query`**: Results are written as JSONL; output format defaults to `tsv` and `csv` is replaced by `tsv`; the `new-name` choice of `-e`/`--existing` is removed as it overlaps with `-T`/`--timestamp`
- **`index_db`**: YAML I/O uses the libyaml loader and dumper when available, and sample uniqueness is checked by key lookup instead of a linear scan; large index definitions load and save much faster
- **`SpanManager`**: Constraint assertions replaced by explicit `ValueError` so guards survive `python -O`
- **Help messages**: Reviewed and clarified across commands
- **Code style**: `black` formatting applied across the package
- **Documentation**: Contributing and development guides updated
- **`compose`**: Simplified options; `--run-id` renamed to `--session-id`; layout file replaces fingerprint
- **`profile`**: Simplified output file naming
- **Execution time**: Printed at the end of each command
- **Logging**: Updated log levels and output formatting across all commands
- **`index_ops`**: Refactored for cleaner path management, clearer plan reporting, and reduced duplication
- **Terminology**: Removed internal `span` wording from user-facing output for clarity
- **Version single-source**: Package version now defined once in `pykmhelpers/_version.py`; `pyproject.toml` reads it dynamically

### Fixed

- Path handling in `plan` and `apply`
- Various bug fixes in `list`
- Python 3.11 compatibility: replaced nested same-quote f-strings (3.12+ syntax) in `composer.py` and `index_db.py`
- Small samples are no longer rejected: span dispatch falls back to span 1 when the k-mer count is below the base
- Minor issues and error handling in `profile` span profiling
- Relative path handling when scanning a directory, and `base_path` no longer forced to the current directory
- Aggregation failure on queries (issue #16)
- Batched queries when the sequences do not end with a newline
- Result path used by `load_query_results`
- `KMHELPERS_LOG_LEVEL` was not parsed as an integer

## [0.6.2] - 2026-04-23

### Added

- **`apply` Command**: New primary command for building k-mer indices from definition files
  - Accepts one or more index definition files (`.json`/`.yaml`) as input
  - Config file support via `-c`/`--config` 
  - Span selection (`--span`) to build only specific k-mer spans (single, comma-separated, or range)
  - Index name filtering (`--name`/`-n`) to build a subset of declared indices
  - `--from` option to reuse build parameters from a parent index
  - Dry-run mode (`--dry-run`) that outputs a ready-to-execute bash script
  - Plan mode (`--plan`) like dry-run but with upfront path validation
  - Progress bar (`--show-progress`) with elapsed time and estimated remaining time
  - Email notification on exit (`--notify EMAIL`) via sendmail (success, failure, or timeout)
  - `--fail-on-error` flag to abort on first failure instead of continuing
  - `--skip-compression` to bypass intermediate file compression when I/O is not a bottleneck
  - `--existing` policy for handling pre-existing unregistered index folders (fail, register, rename, replace…)
  - SIGTERM handling for graceful interruption

- **`list` Command**: Recursively scan a directory and produce a YAML sample manifest
  - Grouped mode (samples grouped by leaf folder) and flat mode (one file = one sample)
  - Integrated k-mer counting via `KmerCounter` (ntcard)
  - File checksum tracking for cache invalidation
  - Persistent cache (`core/cache.py`) to skip re-counting unchanged files across runs

- **Registry `relink` Subcommand**: Update stored paths for registered indices after moving files
  - Relink a single index by ID, or relink all registered indices at once

- **`test extract-dataset` Subcommand**: Extract random sequences from an existing registry to build a test dataset

- **`about` Command**: Display version information and ASCII art banner

- **Mail Notifier** (`pipeline/mail_notifier.py`): Wrapper around `sendmail` supporting subject, body, and file attachments

- **Cache** (`core/cache.py`): Append-only, file-backed key-value store used to persist k-mer counts between runs

### Changed

- **Build Command Renamed**: `build` is now `build-subindex` for clarity
- **`kmhelpersctl.sh` Removed**: The companion bash helper script has been retired; all functionality is available through the `kmhelpers` CLI
- **Query Command**: Significant improvements
  - Score threshold filtering (`--threshold`/`-T`, default 0.05)
  - Batch query mode (`--batch-query`/`-b`): treat all sequences across files as a single query
  - Multiple output formats: `json`, `yaml`, `md`, `html`, `csv` (`--format`/`-f`)
  - Print results to console (`--print`/`-p`) in addition to writing to disk
  - Timestamp suffix on output directory (`--timestamp`/`-P`) to avoid overwriting previous results
  - Conflict resolution for existing result directories (`--existing`/`-e`): skip, fail, delete, or new-name
  - Query method selection (`--method`/`-M`): `seq` (parallelises across sequences) or `sub` (across sub-indices)
  - Read query sequences from stdin by passing `-` as a query file
  - Recursively scan directories for query files
- **Registry Commands**: Run against the current working directory by default (no need to pass `-r .`)
- **Registry `remove` Subcommand**: Now accepts multiple index IDs in one invocation; added `--yes`/`-y` flag to skip the confirmation prompt
- **`--force` Option**: Moved from subcommands to the root `kmhelpers` CLI
- **Verbosity Levels**: Revised log level mapping for more consistent output
- **Global Config Option**: New `-C` flag at the root CLI level to pass a config file to all subcommands
- **KmerCounter**: Refactored to derive from the `Wrapper` base class for consistent process management

### Fixed

- Fixed bugs in the `apply` and `query` pipelines
- Various edge cases in registry operations
- Crash dump output on unhandled exceptions for easier debugging

## [0.6.1] - 2026-03-03

### Added

- **Index Composition and Building**: Complete restructuring of index build pipeline
  - New `kmhelpers compose` command for building composed indices
  - Support for partitioning options in index composition
  - Parameters for splitting larger indices into smaller sub-indices
  - Improved index size management and partitioning strategies

- **Index Definition Format**: Enhanced YAML-based index definition structure
  - New structured YAML format for index definitions 
  - Version tracking with `KMHELPERS_VERSION` constant
  - Improved index definition serialization and deserialization

- **Span Operations**: New span management capabilities
  - Merge commands for definition files
  - Update span serialization for better compatibility
  - Summary log improvements for span operations

- **Build Command Enhancements**:
  - New build options for improved control
  - Better alignment between Builder and Wrapper implementations
  - Split index building capabilities
  - Improved parameter handling in build process

### Changed

- **Wrapper Implementation**: Complete refactoring of KmindexWrapper
  - Improved wrapper architecture and method organization
  - Better integration with Builder class
  - Enhanced logging throughout wrapper operations
  - More consistent parameter handling

- **Builder Class**: Alignment with new wrapper implementation
  - Updated builder to work with new Wrapper interface
  - Improved index building pipeline

- **Logging System**: Comprehensive logging improvements
  - Integrated logging logic across modules
  - Better log messages and tracing
  - Color-coded logging output for improved readability

- **Command Structure**: Reorganized CLI command groups
  - Better command organization and grouping
  - Removed unused interactive mode
  - Improved help messages and command descriptions

### Fixed

- **Error Handling**: Filter Exit exception from fatal error handling
  - Better exception handling in command execution
  - Improved error reporting to users

- **Build Process**: Various bug fixes in index building
  - Fixed issues in span grouping
  - Corrected Bloom Filter specs calculation
  - Improved parameter validation

- **Deprecated Code**: Updated and removed deprecated code patterns
  - Modernized code to follow current best practices
  - Minor feature improvements alongside deprecation fixes

### Deprecated

- Unused interactive mode removed from build process

## [0.5.7] - 2026-01-16

### Added

- **Sequence Methods**: New sequence generation and analysis capabilities
  - `fill_random_kmers()`: Generate sequences with n unique consecutive k-mers
  - `fill_random_and_count_kmers()`: Generate random sequences and count distinct k-mers
  - Sliding window approach ensures true consecutive k-mers with guaranteed uniqueness

- **Test Database Generation**: New `kmhelpers test create-db` command
  - Generate test databases with sample sequences and k-mer statistics
  - Tracks distinct k-mer counts for each sample
  - Outputs FASTA files and samples.yaml metadata file
  - Supports customizable k-mer size for analysis

- **CLI Refactoring**: Complete modularization of CLI structure
  - Moved all groups and commands into separate modules for better maintainability
  - `fof.py`: File-of-Files management commands
  - `test.py`: Test data generation commands
  - `registry.py`: Index registry management commands
  - `project.py`: High-level project workflow commands
  - `build.py`: Index building command
  - `compression.py`: Compression commands (merged compress and kmindex-compress)
  - `query.py`: Query command
  - `shared.py`: Shared utilities (estimate_build_size, config helpers)
  - Main `kmhelpers.py`: Minimal entry point registering all subcommands
  - Reduced main CLI file from 2,017 to 136 lines

### Changed

- **CLI Structure**: Improved code organization and maintainability
  - Each CLI group now in its own focused module
  - Better separation of concerns
  - Easier to locate and modify specific functionality
  - Cleaner imports and dependencies

- **Build Command**: Enhanced with better size estimation
  - Improved calculation logic for resource planning
  - Better error handling in estimation

### Fixed

- Import paths and module organization for CLI commands
- Fixed batch processing in update script

## [0.5.6] - 2026-01-15

### Added

- **IndexBuilder Methods**: Enhanced index building capabilities
  - `create_subindex_from_spans()`: Build indices from genome spans
  - Better integration with project workflow

- **Sequence Operations**: New random sequence generation
  - `Sequence.fill_random()`: Generate random FASTA sequences
  - Used for test data creation and benchmarking

- **KmindexRegistry Compression**: New compression method
  - `registry.compress()`: Compress indices managed in registry
  - Streamlined compression workflow for registered indices

- **Test Data Methods**: Random sample generation utilities
  - `Fasta.create_random_test_dataset()`: Generate random test sequences
  - Support for customizable sequence sizes and counts

### Changed

- **Size Estimation**: Improved build size calculation
  - More accurate estimation logic
  - Better parameter handling for bloom size and abundance cells
  - Enhanced feedback to users during build planning

- **Project Shell**: Interactive shell improvements
  - Better command handling
  - Enhanced user interface

### Fixed

- Size comparison calculations in compression metrics
- Path handling in build output directory

## [0.5.5] - 2026-01-06

### Added

- **Conda Environment Configuration**: New `conda/environment.yml` for easy installation with bioconda
  - Pre-configured with kmindex >= 0.5.3 from bioconda
  - One-command setup: `conda env create -f conda/environment.yml`

- **kmindex Runtime Check**: New `Bin.check_kmindex()` method for better dependency management
  - Validates kmindex availability in PATH
  - Provides helpful error messages with installation instructions
  - Supports both bioconda and source-compiled installations

### Changed

- **README.md Installation Instructions**: Enhanced with multiple installation methods
  - Added conda quick-start section
  - Added pip installation with manual kmindex setup
  - Added detailed "Override kmindex Installation" section for users with custom-compiled versions
  - Updated Quick Start with runtime check example

### Fixed

- Added `fof_validation.py` to validate FOF syntax

## [0.5.4] - 2025-12-23

### Added

- All classes from operations module now properly exported in `__init__.py` files
- Comprehensive import test suite (`test_imports.py`) to validate package structure
- Explicit package configuration in `pyproject.toml` for proper wheel building

### Changed

- Fixed circular import in `operations.builder` module
  - Changed `from ..operations import FofManager` to `from .fof import FofManager`

### Fixed

- Fixed missing `bloom_filter.py` in installed package
  - Updated `pyproject.toml` to explicitly list all subpackages in build configuration
- Resolved circular import issue preventing proper package initialization
- All imports now work correctly from top-level `kmhelpers` package

## [0.5.3] - 2025-12-23

### Added

- Enhanced package structure and stability

### Changed

- Minor improvements and updates

### Fixed

- Various bug fixes and improvements

## [0.5.2] - 2025-12-15

### Added

- **IndexBuilder**: New class for managing index build operations
  - `create_subindex()`: Core method for building indices with streamlined parameters
  - Integrated into package exports for easy access

- **Sequence Operations**: Enhanced sequence management capabilities
  - New `Sequence` module in operations for handling k-mer sequences
  - Query operations integration with sequences
  - Updated query module with sequence support

- **Improved Index Management**:
  - Enhanced Index class methods for better object manipulation
  - Better property handling and access patterns

### Changed

- **Wrapper Refactoring**: Reduced coupling in KmindexWrapper
  - Improved separation of concerns
  - Better method organization
  - Cleaner interface for index operations

- **Operations Updates**:
  - Updated builder operations for consistency
  - Improved FOF handling
  - Enhanced sequence and query integration

### Fixed

- Fixed index property access patterns
- Improved error handling in builder operations
- Better integration between sequence and query modules

## [0.5.1] - 2025-12-10

### Added

- **KmindexWrapper Enhancements**: Improved wrapper functionality
  - Better command monitoring
  - Enhanced parameter handling
  - Improved error reporting

### Changed

- Refactored KmindexWrapper for reduced coupling
  - Better method decomposition
  - Improved code maintainability
  - Cleaner internal architecture

- Updated FOF operations:
  - Enhanced file handling
  - Better validation

### Fixed

- Fixed FOF file processing issues
- Improved sequence query integration

## [0.5.0] - 2025-12-05

### Added

- **Sequence Management**: Complete sequence handling system
  - New `Sequence` class for managing k-mer sequences
  - Query operations with sequence support
  - Integration with index operations

- **Index Object Methods**: Enhanced index manipulation
  - Methods to work with index as Python objects
  - Better property access patterns
  - Improved index lifecycle management

### Changed

- Updated `IndexBuilder` class:
  - Improved build pipeline structure
  - Better parameter management
  - Enhanced error handling

- Refactored core modules for better organization

### Fixed

- Various improvements in index handling
- Better error messages and validation

## [0.4.0] - 2025-11-25

### Added

- **Object-Oriented Index Interface**: Complete rewrite of index handling
  - Enhanced `KmtricksIndex` with object manipulation methods
  - New methods for working with index as Python objects
  - Better property access and management

- **IndexBuilder Class**: New builder class for index operations
  - Streamlined index building process
  - Better parameter handling
  - Integration with KmindexWrapper

### Changed

- Updated `KmindexWrapper` implementation
- Improved sample generation with folder support
- Enhanced builder module with new capabilities

### Fixed

- Index builder property handling
- Sample generation path issues

## [0.3.0] - 2025-11-20

### Added

- **KmindexWrapper**: High-level interface for building and querying kmindex indices
  - `build()` method wraps kmindex build with all parameters
  - `query()` method wraps kmindex query functionality
  - Automatic handling of required parameters (`-d/--run-dir`, `-r/--register-as`)
  - Returns `KmtricksIndex` objects for easy property access
  - Support for both presence/absence and abundance indexing

- **FofManager**: Comprehensive file-of-files (FOF) management class
  - `create_fof_file()`: Create FOF from list of files with smart sample name extraction
  - `create_fof_from_directory()`: Auto-discover and create FOF from directory
  - `list_files_in_directory()`: List files matching bioinformatics extensions
  - `load_fof_file()` / `get_sample_ids()`: Load sample IDs from FOF
  - `load_with_paths()`: Load samples with their file paths as dictionary
  - `validate_fof_file()`: Comprehensive FOF format validation
  - `validate_input_files()`: Batch file existence checking
  - `extract_sample_name()`: Smart extraction removing common extensions (.fasta.gz, .fastq.gz, etc.)
  - `append_to_fof()`: Append files to existing FOF
  - `copy_fof()`: Copy FOF files
  - Support for recursive directory scanning
  - Configurable file extension filtering

- **New core module**: `kmhelpers/core/wrapper.py` for KmindexWrapper
- **New operations module**: `kmhelpers/operations/fof.py` for FofManager
- **Example script**: `examples/index_fake_samples.py` demonstrating new wrapper usage
- **Example data**: `examples/data/fake_samples/` with synthetic FASTA files for testing

### Changed

- Updated `KmindexWrapper` to use `FofManager` for FOF operations
- Type annotations improved using `Sequence` instead of `List` for better type compatibility
- Updated package version to 0.3.0 in `__init__.py`
- Enhanced README.md with comprehensive documentation for new features
- Added quick start section for building indices
- Updated API reference with KmindexWrapper and FofManager documentation

### Fixed

- Fixed kmindex build command to always include required `-d/--run-dir` parameter (defaults to `.kmindex_run`)
- Fixed kmindex build command to always include required `-r/--register-as` parameter (defaults to index basename)
- Added validation to check if `run_dir` already exists to prevent build errors
- Fixed type compatibility issues with file list parameters using `Sequence` type hint
- Corrected FOF format to use "name: path" (with colon separator) instead of just path

### Documentation

- Updated README.md with new features section
- Added FOF management examples
- Added index building examples with KmindexWrapper
- Updated project structure documentation
- Updated API reference with new classes and methods
- Updated examples/data/fake_samples/README.md with corrected kmindex parameters

## [0.2.0] - 2024-11-19

### Added

- **Type Annotations**: Complete type annotations for all methods in `utils.py`
- **Index Structure Validation**:
  - `check_index_structure()`: Comprehensive validation of index directory structure
  - `create_registry_from_folder()`: Auto-discover and register multiple indices from a folder
- **Binary Version Management**:
  - `get_kmindex_version()`: Wrapper to retrieve kmindex version
  - Optional binary checks with `Main.init(check_bins=False)`
- **Index Registry Improvements**:
  - Better error handling and validation
  - Fixed bugs in index property loading
  - Improved JSON import/export
- **Installation Tools**:
  - `install_kmindex.sh`: Script to install kmindex without server dependencies
  - Improved dependency checking
- **Compression Enhancements**:
  - Support for compressing indices outside their directory
  - Improved BitmatrixShuffle wrapper calls
  - Added reverse permutation validation tests
  - Enhanced size comparison path handling
- **Examples**:
  - `compress_selection.py`: Example for selective partition compression
  - Sample data added for testing
  - Bash script to run examples

### Changed

- **Binary Management**:
  - Updated PATH management system for external binaries
  - More flexible binary location handling
- **Class Renaming**:
  - Internal class reorganization for consistency
- **Compressor Updates**:
  - Multiple iterations of compressor improvements
  - Better API for compression operations
  - Enhanced metrics collection
- **Index Parameter**: Made index a required input parameter for operations
- **Setup.py**: Multiple updates for better package configuration

### Fixed

- Type issues in index property handling
- Path handling for size comparison files
- Package installation issues
- Index registry bugs
- JSON index import issues
- Misindenting in core modules
- Binary check dependency issues

### Documentation

- Improved log messages for index structure validation
- Updated documentation for new features
- Corrected incorrect information in API docs
- Added author information

## [0.0.1] - 2024-10-28

### Restructured

- **Complete project reorganization** for better maintainability and professionalism
  - Created modular package structure with `core/`, `operations/`, `metrics/`, and `cli/` submodules
  - Moved `kmhelpers.py` → `kmhelpers/core/utils.py`
  - Organized related functionality into logical modules
  - Added proper `__init__.py` files for clean package imports

### Added

- **Comprehensive README.md** with:
  - Project overview and features
  - Installation instructions
  - Quick start guide
  - Complete API reference
  - Multiple usage examples
  - Performance tips and troubleshooting

- **setup.py** for proper Python package installation
  - Support for `pip install -e .`
  - Console script entry points (`kmhelpers-query`, `kmhelpers-compress`)
  - Proper dependencies declaration

- **Documentation**:
  - `examples/basic_usage.py` - Basic usage example

### Deprecated

- Direct script execution (still works but CLI commands preferred):
  ```bash
  # Old
  python query_index.py

  # New
  kmhelpers-query  # or python -m kmhelpers.cli.query_index
  ```

## Project Structure

```
kmhelpers/
├── kmhelpers/              # Main package
│   ├── core/              # Core functionality
│   │   ├── utils.py       # Binary management, utilities, kmindex operations
│   │   └── index.py       # Index and IndexRegistry classes
│   ├── operations/        # Compression operations
│   │   └── compressor.py  # Compressor class
│   ├── metrics/           # Performance metrics
│   │   └── compression_metrics.py
│   └── cli/               # Command-line tools
│       ├── compress_index.py
│       ├── query_index.py
│       └── register_index.py
├── examples/              # Usage examples
├── tests/                 # Unit tests
├── docs/                  # Documentation
├── setup.py              # Package installation
└── README.md             # Main documentation
```

