# How an index is built

## From sample files to an index

[`design`](../commands/design.md) decides how the index is organized, from the sizes of the
samples; [`build`](../commands/build.md) decides how to build it on this machine (or a
cluster), then builds it. `design` runs three commands and `build` two, which can also be
run one by one (see the [step-by-step tutorial](../tutorials/ecoli_steps.md)).

```mermaid
flowchart TD
    F["sample files"] -->|"list: count k-mers"| L["sample list<br/>(k-mers per sample)"]
    L -->|"profile: size classes"| PR["spans, then groups"]
    PR -->|"compose: index definition"| C["shards, session, layout"]
    C -->|"plan: decide the build"| PL["parts, chunks, jobs<br/>plan.yaml + scripts"]
    PL -->|"apply: kmtricks, one run per chunk"| R["runs"]
    R -->|"apply: merge, publish"| I["index: one folder per shard<br/>+ index.json"]

    subgraph design
        L
        PR
        C
    end
    subgraph build
        PL
        R
    end
```

1. **list** counts the k-mers of each sample ([K-mer counting](kmer-counting.md)).
2. **profile** sorts the samples into spans by k-mer count, then merges consecutive spans
   into groups, balancing storage ([profile](../commands/profile.md#description)).
3. **compose** writes the index definition: the shards of each group, the samples this
   session adds to each shard, and the layout, kept for later updates.
4. **plan** takes every build decision from the resources available: partitions, threads,
   whether a part is built in one run or in chunks, how chunks are merged, and the jobs.
   It builds nothing ([plan](../commands/plan.md)).
5. **apply** runs the plan: each chunk is one kmtricks run; the runs of a shard are merged,
   then published into the index, and checked ([apply](../commands/apply.md)).

## Why shards and chunks

Both cut the samples into smaller sets, for different reasons:

| | Shard | Chunk |
|---|-------|-------|
| what | a slice of a group, kept in the index | a slice of the samples of one build, merged afterwards |
| why | keep each index of the samples bounded, as the index grows | fit one kmtricks run in the open-files and memory limits of a machine |
| decided by | `design` (`--sb`), once for the life of the index | `plan` (`--cb`, the resources), at each build |
| visible in the index | yes: one folder per shard | no: only its shard is |

See [compose - Sharding](../commands/compose.md#description) and
[build - Shards and chunks](../commands/build.md#shards-and-chunks).

## On a cluster

With `--hpc cluster.yaml`, `plan` sizes the build for the jobs of a SLURM cluster, and the
jobs run the plan: chunks on several nodes at once, then one merge per shard. See
[build - On a cluster](../commands/build.md#on-a-cluster).

```mermaid
sequenceDiagram
    actor U as you
    participant B as build --hpc
    participant SL as SLURM
    participant A as build jobs (array)
    participant M as merge job, per shard
    participant F as finish job
    U->>B: coli_db -o coli_build/ --hpc cluster.yaml
    B->>B: plan: chunks, jobs, SLURM files
    B->>SL: submit the array, the merges, the finish job
    B-->>U: submitted (build exits)
    par on several nodes
        SL->>A: one task per job: its chunks (kmtricks)
    end
    A-->>SL: done
    SL->>M: once the jobs of its shard are done
    M->>M: merge the chunks, publish the shard
    SL->>F: once every job has ended
    F->>F: check the index, write progress.yaml
    F-->>U: mail (with --notify)
    U->>B: apply --status --sp, at any time
```

A failed job cancels the jobs waiting on it, and the finish job reports it; running the same
`build` command again submits only what is not done.

## Updating an index

An update is a new session: its samples are added to the shards of the existing layout, so
that the index keeps its groups, Bloom filter sizes and partitions.

```mermaid
sequenceDiagram
    actor U as you
    participant D as design -s update
    participant B as build -s update
    participant S as shard coli_g0 (in the index)
    U->>D: new sample files
    D->>D: assign each sample to its group and shard (layout)
    U->>B: build the session
    B->>B: build the new samples (one run, or chunks)
    B->>B: merge them with the current coli_g0
    Note over S: coli_g0 stays queryable
    B->>S: swap: the merged version replaces coli_g0
    B->>B: check it, then delete the previous version
```

The swap takes a second or so; until then, queries see the previous version. An
interrupted update is finished by running the same command again. See
[build - Updating an index](../commands/build.md#updating-an-index) and the
[update tutorial](../tutorials/ecoli_update.md).
