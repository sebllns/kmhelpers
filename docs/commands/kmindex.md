# kmindex

Low-level wrapper commands for direct interaction with kmindex.

## Usage

```
kmhelpers kmindex COMMAND [ARGS]...
```

## Description

`kmindex` provides thin wrappers around the underlying `kmindex` binary. For most workflows, prefer the higher-level commands ([`apply`](apply.md), [`query`](query.md), [`compress`](compress.md)) which add registry management, progress reporting, and error handling.

## Subcommands

| Subcommand | Description |
|------------|-------------|
| `build` | Build a k-mer index directly from a FOF file |
| `query` | Query indices with FASTA/FASTQ sequences |

## Examples

```bash
# Build an index from a FOF file
kmhelpers kmindex build -f samples.fof -o ./index -k 31

# Direct query
kmhelpers kmindex query -i ./index -q query.fa -o results
```