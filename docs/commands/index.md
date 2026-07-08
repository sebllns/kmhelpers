# Command Reference

**kmhelpers** commands cover the full k-mer index lifecycle: build indices from raw sequences, then query them. Most workflows **only need three top-level commands** — **`design`**, **`build`**, and **`query`**. Click on any command below to see its full options, inputs/outputs, examples, and additional information.

## Main Pipeline

| Command | Description |
|---------|-------------|
| [`design`](design.md) | Discover samples, profile them, and compose index definitions (steps: `list` → `profile` → `compose`) |
| [`build`](build.md) | Validate paths and build indices (steps: `plan` → `apply`) |
| [`query`](query.md) | Query indices with FASTA/FASTQ sequences |
| [`compress`](compress.md) | Compress an index managed in a registry *(under development)* |

## Design (manual steps)

Steps run internally by [`design`](design.md):

| Command | Description |
|---------|-------------|
| [`list`](list.md) | Step 1 — scan a directory and count k-mers |
| [`profile`](profile.md) | Step 2 — compute Bloom-filter distribution |
| [`compose`](compose.md) | Step 3 — generate index definition files |

## Build (manual steps)

Steps run internally by [`build`](build.md):

| Command | Description |
|---------|-------------|
| [`plan`](plan.md) | Step 1 — validate paths and preview the build plan |
| [`apply`](apply.md) | Step 2 — build k-mer indices |

## Utilities

| Command | Description |
|---------|-------------|
| [`registry`](registry.md) | Manage k-mer index registries |
| [`pipeline`](pipeline.md) | Run a sequence of commands defined in a YAML pipeline file |

## Global Options

These options are available on the root `kmhelpers` command and apply to all subcommands:

```
-C, --config FILE    YAML config file for default values  [env var:
                     KMHELPERS_CONFIG]
-v, --verbose        Increase verbosity: -v for DEBUG
-q, --quiet          Decrease verbosity: -q for WARNING, -qq for ERROR, -qqq
                     for CRITICAL
--no-log-formatting  Disable log formatter  [env var:
                     KMHELPERS_NO_LOG_FORMATTING]
-L, --log-file FILE  Path to log file (logs will be written in addition to
                     console output)  [env var: KMHELPERS_LOG_FILE]
--chdir DIRECTORY    Change to directory before initialization  [env var:
                     KMHELPERS_RUN_DIR]
-y, --yes            Automatically answer yes to all confirmation prompts.
                     [env var: KMHELPERS_SKIP_CONFIRMATION]
```

Also honors `KMHELPERS_LOG_LEVEL`: default log level 0-4 (0=CRITICAL, 4=DEBUG) before `-v`/`-q` adjustments. Default: 3 (INFO).