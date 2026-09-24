# build

## Synopsis

Validate paths then build k-mer indices from an index definition file in a single command.

!!! abstract "USAGE"
    ```
    kmhelpers build [OPTIONS] INPUT_FILE
    ```

    | Argument | Description |
    |----------|-------------|
    | `INPUT_FILE` | Index definition file `COMPOSE_DIR/NAME/SESSION/NAME.yaml` written by `compose` or `design` (required) |
    | `-o, --output-dir BUILD_DIR` | Index directory: receives the built index, reused across builds and passed to `query -r` (required) |

!!! abstract "I/O"
    **Input:** `COMPOSE_DIR/NAME/SESSION/NAME.yaml` written by `compose`, or `DESIGN_DIR/compose/NAME/SESSION/NAME.yaml` when produced by `design` (see [design - Next Step](design.md#next-step))  
    **Output:** Bloom filters in `BUILD_DIR/kmindex_data/SESSION/`, registered in `BUILD_DIR/index.json`

## Advanced Options

| Option | Description |
|--------|-------------|
| `-b, --base-path DIR` | Base path to resolve relative sample paths |
| `--minim-size INT` | Minimizer size (default: 10) |
| `-t, --threads INT` | Number of threads |
| `-p, --partition-count INT` | Override number of partitions |
| `-NC, --skip-compression` | Skip compression of intermediate files during index building (useful on slow disks) |
| `-SP, --show-progress` | Enable animation that shows the current subindex being built (use in an interactive shell) |
| `--notify EMAIL` | Send email notification on exit (requires sendmail) |

## Paths

Two directories are involved, and they are distinct:

- `COMPOSE_DIR` holds the index definitions. It is the `-o` of `compose`, or `DESIGN_DIR/compose/` when using `design`.
- `BUILD_DIR` holds the built index. It is the `-o` of `build`, and the `-r` of `query`.

```
coli_db/                          DESIGN_DIR (design -o)
└── compose/                      COMPOSE_DIR
    ├── coli_layout.yaml
    └── coli/                     NAME
        ├── initial/              SESSION (design/compose -S)
        │   └── coli.yaml         INPUT_FILE for build
        └── update/
            └── coli.yaml

coli_build/                       BUILD_DIR (build -o, query -r)
├── index.json                    registry of all built indices
├── kmindex_data/
│   ├── initial/                  Bloom filters, one folder per SESSION
│   │   └── coli_g0/              previous version, kept after the update
│   └── update/
│       └── coli_g0/              merged version (initial + update samples)
├── assets/                       generated kmindex scripts
└── logs/
```

Reuse the same `BUILD_DIR` for every session of an index: each build adds its sub-indices to `BUILD_DIR/index.json`. The Bloom filter folder is named after the `SESSION` directory of `INPUT_FILE`, so a session can only be built once into a given `BUILD_DIR`.

## Description

`build` chains [`plan`](plan.md) and [`apply`](apply.md) into a single invocation. It is equivalent to running the two commands in sequence.

**Step 1 - plan:** validates all sample paths upfront and writes the equivalent `kmindex` shell script to `BUILD_DIR/assets/` and a validation report to `BUILD_DIR/logs/`. Fix any path errors before the build starts rather than discovering them mid-run.

**Step 2 - apply:** executes the build and registers all completed indices in `BUILD_DIR/index.json`.

**Filtering** - `build` always processes every index declared in `INPUT_FILE`. Use [`plan`](plan.md) and [`apply`](apply.md) with `--name` or `--span` to build a subset.

**Notifications** - use `--notify` to receive an email when the build exits (requires `sendmail`). The notification is sent on both success and failure, including on `SIGTERM`.

### Updating an index

Building a new `SESSION` into a `BUILD_DIR` that already holds the same index triggers a `kmindex merge`. `kmindex` cannot add samples to an existing index in place, so an update merges the previous samples and the new ones into a **new** index:

- The updated index `NAME_gN`, holding the previous samples plus the new ones, is written to `BUILD_DIR/kmindex_data/<new session>/NAME_gN/`. It keeps its name in `index.json`, so queries need no change.
- The files of the previous version are left at `BUILD_DIR/kmindex_data/<previous session>/NAME_gN/`. They are no longer registered, so queries ignore them.
- Only the sub-indices that receive new samples are merged. The others stay where they were built, still registered and untouched.

!!! warning "Disk space"
    Both versions coexist on disk, during and after the merge. Plan for at least twice the size of the sub-indices being updated.

The previous version is not deleted on purpose, so the updated index can be validated first. Once validated, delete its directory to reclaim the space:

```bash
# Registered indices and the samples they hold
kmhelpers manage -r coli_build/ list
kmhelpers manage -r coli_build/ info -n coli_g0

# Leftover files of the previous version, delete once validated
rm -rf coli_build/kmindex_data/initial/coli_g0
```

Delete the sub-index directory, not the whole session directory: a session folder can still hold sub-indices that were not merged and are in use.

## Examples

```bash
# Build the index defined by design/compose in session "initial"
kmhelpers build coli_db/compose/coli/initial/coli.yaml -o coli_build/

# Add an update session to the same index directory
kmhelpers build coli_db/compose/coli/update/coli.yaml -o coli_build/

# Set threads and show progress
kmhelpers build coli_db/compose/coli/initial/coli.yaml -o coli_build/ -t 8 -SP

# Notify by email when done
kmhelpers build coli_db/compose/coli/initial/coli.yaml -o coli_build/ --notify user@example.com
```

## See Also

- [`plan`](plan.md) - plan step only
- [`apply`](apply.md) - apply step only
- [`design`](design.md) - design the index before building
- [`query`](query.md) - query the index in `BUILD_DIR`
