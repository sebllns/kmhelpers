# Command Reference

kmhelpers commands cover the full k-mer index lifecycle: build indices from raw sequences, then query them. Most workflows only need three top-level commands — `design`, `build`, and `query`.

## Main Pipeline

| Command | Description |
|---------|-------------|
| [`design`](design.md) | Discover samples, profile them, and compose index definitions (steps: `list` → `profile` → `compose`) |
| [`build`](build.md) | Validate paths and build indices (steps: `plan` → `apply`) |
| [`query`](query.md) | Query indices with FASTA/FASTQ sequences |
| [`compress`](compress.md) | Compress an index managed in a registry *(under development)* |

## Design Pipeline (steps)

Steps run internally by [`design`](design.md):

| Command | Description |
|---------|-------------|
| [`list`](list.md) | Step 1 — scan a directory and count k-mers |
| [`profile`](profile.md) | Step 2 — compute Bloom-filter span distribution |
| [`compose`](compose.md) | Step 3 — generate index definition files |

## Build Pipeline (steps)

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
-C, --config FILE       YAML config file for default values
-v, --verbose           Increase verbosity (-v DEBUG)
-q, --quiet             Decrease verbosity (-q WARNING, -qq ERROR, -qqq CRITICAL)
-L, --log-file FILE     Write logs to a file
-y, --yes               Skip confirmation prompts
--chdir DIR             Change to directory before initialization
--no-log-formatting     Disable colored log output
```