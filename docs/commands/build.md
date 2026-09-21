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
    **Input:** `COMPOSE_DIR/NAME/SESSION/NAME.yaml`  
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
│   └── update/
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
