# Command Reference

## Main Commands

### Design pipeline

| Command | Description |
|---------|-------------|
| [`design`](design.md) | Run the full list → profile → compose pipeline in a single command |
| &nbsp;&nbsp;↳ [`list`](list.md) | Step 1 — scan a directory and count k-mers |
| &nbsp;&nbsp;↳ [`profile`](profile.md) | Step 2 — compute Bloom-filter span distribution |
| &nbsp;&nbsp;↳ [`compose`](compose.md) | Step 3 — generate index definition files |

### Build pipeline

| Command | Description |
|---------|-------------|
| [`build`](build.md) | Validate paths then build indices from definition files (plan → apply) |
| &nbsp;&nbsp;↳ [`plan`](plan.md) | Step 1 — validate paths and preview the build plan |
| &nbsp;&nbsp;↳ [`apply`](apply.md) | Step 2 — build k-mer indices |

### Query & compress

| Command | Description |
|---------|-------------|
| [`query`](query.md) | Query indices with FASTA/FASTQ sequences |
| [`compress`](compress.md) | Compress an index managed in a registry |

## Utilities

| Command | Description |
|---------|-------------|
| [`registry`](registry.md) | Manage k-mer index registries |
| [`pipeline`](pipeline.md) | Run a sequence of commands defined in a YAML pipeline file |

## Global Options

These options are available on the root `kmhelpers` command and apply to all subcommands:

```
-C, --config FILE       YAML config file for default values
-v, --verbose           Increase verbosity (-v INFO, -vv DEBUG)
-q, --quiet             Decrease verbosity (-q ERROR, -qq CRITICAL)
-L, --log-file FILE     Write logs to a file
-y, --yes               Skip confirmation prompts
--chdir DIR             Change to directory before initialization
--no-log-formatting     Disable colored log output
```