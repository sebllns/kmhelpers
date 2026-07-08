# Quick Start

Once kmhelpers is [installed](installation.md), the fastest way to get hands-on is the [E. coli tutorial](tutorials/ecoli.md) — it builds a queryable index from real data in three commands. For syntax and options on any command, see the [Command Reference](commands/index.md).

> **Tip:** `kh` is available as a short alias for `kmhelpers` — both commands are identical.

## The Pipeline

Indices are built and queried in three steps:

```
design → build → query
```

![Pipeline diagram](diagrams/fig_pipeline.svg)

| Command | Purpose |
|---------|---------|
| [`design`](commands/design.md) | Discover samples and generate index definitions |
| [`build`](commands/build.md) | Build k-mer indices from those definitions |
| [`query`](commands/query.md) | Search the indices with FASTA/FASTQ sequences |

## Next Steps

- **[Tutorial](tutorials/ecoli.md)** — a full hands-on walkthrough indexing 10 *E. coli* assemblies
- **[Command Reference](commands/index.md)** — detailed syntax and options for every command
- **[Step-by-step breakdown](tutorials/ecoli_steps.md)** — run the internal steps (`list`, `profile`, `compose`, `plan`, `apply`) individually for finer control
