# Command Reference

## Main Commands

| Command | Description |
|---------|-------------|
| [`list`](list.md) | Recursively scan a directory and produce a YAML sample manifest |
| [`profile`](profile.md) | Analyse a sample YAML file and output a Bloom-filter span profile |
| [`compose`](compose.md) | Compose index definition files from sample lists |
| [`plan`](plan.md) | Preview build plan from index definition files (dry-run with path validation) |
| [`apply`](apply.md) | Build k-mer indices from index definition files |
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