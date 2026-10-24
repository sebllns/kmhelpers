# Command Reference

**kmhelpers** commands cover the full k-mer index lifecycle: build indices from raw sequences, then query them. The terms used here (shard, partition, session, chunk...) are defined in the [Glossary](../concepts/terms.md). Most workflows **only need three top-level commands** - **`design`**, **`build`**, and **`query`**. Click on any command below to see its full options, inputs/outputs, examples, and additional information.

## Main Pipeline

| Command | Description |
|---------|-------------|
| [`design`](design.md) | Discover samples, profile them, and compose index definitions (steps: `list` → `profile` → `compose`) |
| [`build`](build.md) | Plan then build indices (steps: `plan` → `apply`) |
| [`query`](query.md) | Query indices with FASTA/FASTQ sequences |
| [`compress`](compress.md) | Compress the shards of a registry *(under development)* |

## Design (manual steps)

Steps run internally by [`design`](design.md):

| Command | Description |
|---------|-------------|
| [`list`](list.md) | Step 1 - scan a directory and count k-mers |
| [`profile`](profile.md) | Step 2 - compute Bloom-filter distribution |
| [`compose`](compose.md) | Step 3 - generate index definition files |

## Build (manual steps)

Steps run internally by [`build`](build.md):

| Command | Description |
|---------|-------------|
| [`plan`](plan.md) | Step 1 - validate paths, decide the whole build and write the plan (scripts, jobs, SLURM files) |
| [`apply`](apply.md) | Step 2 - run the plan: build and publish the indices |

## Utilities

| Command | Description |
|---------|-------------|
| [`manage`](manage.md) | Manage k-mer index registries *(under development)* |
| [`pipeline`](pipeline.md) | Run a sequence of commands defined in a YAML pipeline file |
| [`check-deps`](check-deps.md) | Check that kmindex, kmtricks and ntcard are callable |
| [`install-deps`](install-deps.md) | Download and install kmtricks, kmindex and ntcard prebuilt binaries |

## Global Options

These options are available on the root `kmhelpers` command and apply to all subcommands:

```
-C, --config FILE         YAML config file for default values  [env var:
                          KMHELPERS_CONFIG]
-V, --verbose             Increase verbosity: -V for DEBUG
-Q, --quiet               Decrease verbosity: -Q for WARNING, -QQ for ERROR,
                          -QQQ for CRITICAL
--NF, --no-log-formatting  Disable log formatter  [env var:
                          KMHELPERS_NO_LOG_FORMATTING]
-L, --log-file FILE       Path to log file (logs will be written in addition
                          to console output)  [env var: KMHELPERS_LOG_FILE]
--chdir DIRECTORY         Change to directory before initialization  [env
                          var: KMHELPERS_RUN_DIR]
-Y, --yes                 Automatically answer yes to all confirmation
                          prompts.  [env var: KMHELPERS_SKIP_CONFIRMATION]
```

Also honors `KMHELPERS_LOG_LEVEL`: default log level 0-4 (0=CRITICAL, 4=DEBUG) before `-V`/`-Q` adjustments. Default: 3 (INFO).

## Configuration file

`-C, --config FILE` (or `KMHELPERS_CONFIG=FILE`) reads default option values from a YAML file, for every command:

```yaml
# kmhelpers.yaml
limits: '{"ram": 120000000000, "threads": 24}'
chunks_per_job: 4
false_positive_rate: 0.25
auto_group_min_gain: 0.25
```

```bash
kmhelpers -C kmhelpers.yaml plan coli_db -o coli_build/
export KMHELPERS_CONFIG=$PWD/kmhelpers.yaml      # same, for every command
```

- **Keys** are the parameter names: the long option name with `_` for `-` (`--chunks-per-job` → `chunks_per_job`). A dashed key (`chunks-per-job`) is ignored without warning. A few options have another parameter name:

    | Option | Key | Commands |
    |--------|-----|----------|
    | `-o, --output-dir` | `work_dir` | `plan`, `apply`, `build` |
    | `-o, --output` | `output_dir` (`profile`), `output_file` (`list`) | |
    | `-s, --session` | `session_id` | `design`, `compose` (`session` in `plan`, `apply`, `build`) |
    | `--sh, --shard` | `index_ids` | `plan`, `query`, `compress` |
    | `--task` | `task_ids` | `apply` |
    | `-g, --group` | `n_groups` | `design`, `profile` |
    | `--ab, --abundance-bits` | `bitw` | `design`, `compose` |
    | `--cluster` | `cluster_file` | `plan` |
    | `-x, --fail-fast` | `fail_on_error` | `plan`, `apply` |
    | `-p, --paired` | `pair_regex` | `design`, `list` |
    | `--continue` | `do_continue` | `list` |

- **One flat mapping for all commands**: a key applies to every command that has this parameter (e.g. `threads`), and is ignored by the others. Options of `manage` subcommands are not read from it.
- **Precedence**: see [below](#precedence). A config file therefore sets the defaults of a site or a project, and any command can still override them.
- Values are typed as on the command line: JSON options such as `limits` are strings, flags are `true`/`false`.
- [`pipeline`](pipeline.md) uses the same file as the base of every step, below the step's own values and `-x KEY VALUE`.

## Environment variables

| Variable | Sets | Commands |
|----------|------|----------|
| `KMHELPERS_CONFIG` | `-C, --config`: the configuration file above | all |
| `KMHELPERS_LOG_LEVEL` | default log level 0-4 (0=CRITICAL, 4=DEBUG, default 3=INFO), before `-V`/`-Q` | all |
| `KMHELPERS_LOG_FILE` | `-L, --log-file` | all |
| `KMHELPERS_NO_LOG_FORMATTING` | `--NF, --no-log-formatting` | all |
| `KMHELPERS_RUN_DIR` | `--chdir`: directory to work in | all |
| `KMHELPERS_SKIP_CONFIRMATION` | `-Y, --yes`: answer yes to every confirmation | all |
| `KMHELPERS_SEED` | seed of the random generator, for reproducible test data | `test` |
| `KMHELPERS_AUTO_GROUP_SAMPLES` | `--auto-group-samples` (default 1000) | `profile`, `design` |
| `KMHELPERS_AUTO_GROUP_MAX` | `--auto-group-max` (default 20) | `profile`, `design` |
| `KMHELPERS_AUTO_GROUP_MIN_GAIN` | `--auto-group-min-gain` (default 0.2) | `profile`, `design` |
| `KMHELPERS_AUTO_GROUP_SINGLE_MAX` | `--auto-group-single-max` (`profile`: none; `design`: 4GB of built index) | `profile`, `design` |
| `KMINDEX_BIN_PATH`, `KMTRICKS_BIN_PATH`, `NTCARD_BIN_PATH` | directory of the tool, put first on `PATH` (see [`check-deps`](check-deps.md)) | all that run the tool |

`design` hides the `--auto-group-*` options: set them with their variables, or in the configuration file. `--help` lists the variable of each option (`[env var: ...]`).

## Precedence

When an option is set in several places, the first one found wins:

1. the **command line** (`--chunks-per-job 0`);
2. the **environment variable** of the option (`KMHELPERS_AUTO_GROUP_MIN_GAIN=0.3`);
3. the **configuration file** (`-C`, `KMHELPERS_CONFIG`);
4. the **default** of the option (as shown by `--help`).

For example, with `auto_group_min_gain: 0.5` in the configuration file, `KMHELPERS_AUTO_GROUP_MIN_GAIN=0.3 kmhelpers -C kmhelpers.yaml profile ...` uses 0.3, and `profile --auto-group-min-gain 0.1` uses 0.1 whatever the variable and the file say.

## Option names

- Global options, given before the command, have uppercase short flags (`-V`, `-Q`, `-Y`, `-C`, `-L`).
- Command options are lowercase. When a letter is already taken in a command, the option gets a short double-dash name instead (`query --thr, --threshold`, `plan --off, --offline`).
- Long names never change.
- Every command takes `-h, --help`, and `-H, --HELP` to also list its hidden (expert) options.