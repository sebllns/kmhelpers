# manage

## Synopsis

Manage k-mer index registries.

!!! abstract "USAGE"
    ```
    kmhelpers manage [OPTIONS] COMMAND [ARGS]...
    ```

    | Argument | Description |
    |----------|-------------|
    | `-r, --registry-path DIR` | Path to kmindex registry (default: current directory) |

!!! abstract "I/O"
    **Input:** kmindex registry (`-r`), subcommand-specific arguments  
    **Output:** updated registry state (create, add, remove, rename, relink, clean) or printed info (list, info, check)

## Subcommands

| Subcommand | Description |
|------------|-------------|
| `create` | Initialise a registry and optionally register existing shards |
| `add` | Register existing kmtricks indexes as shards of an existing registry |
| `list` | List all shards of a registry |
| `info` | Show detailed information about a shard |
| `check` | Validate registry consistency and shard structures |
| `remove` | Remove one or more shards from the registry |
| `rename` | Rename a shard, or an index (all its shards) |
| `relink` | Recreate links after moving shard folders |
| `clean` | Remove build leftovers, finished session plans and logs |

## Subcommand Options

### `create`

| Option | Description |
|--------|-------------|
| `-i, --input-dir DIR` | Directory containing existing kmtricks indices to register |
| `--sh, --shard TEXT` | Shard(s) to register (default: all found) |

### `add`

| Option | Description |
|--------|-------------|
| `-i, --input-dir DIR` | Directory containing kmtricks indices to add (required) |
| `--sh, --shard TEXT` | Shard(s) to register (default: all found) |

### `check`

| Option | Description |
|--------|-------------|
| `--sh, --shard TEXT` | Check only these shards (repeatable, default: all); fails if one is not registered |
| `-v, --verbose` | Show detailed validation output |
| `--nq, --no-query` | Skip the query check |
| `-z, --zvalue INT` | Z-value of the query check (default: 6) |
| `--min-gap FLOAT` | Fail a shard whose positive score minus its negative score is below this (default: 0.5) |
| `--autorepair` | Repair the registry before the checks (see [Autorepair](#autorepair)) |
| `--search DIR` | With `--autorepair`: also look for lost shards in `DIR` (repeatable) |

After the structure checks, `check` takes 10 random (k+z)-mers from the first sample of each shard
(from the sample file listed first in the shard's `kmtricks.fof`), the **positives**, and 10 random
DNA sequences of 1000 bases, the **negatives**. It queries them all in one kmindex query against
the registry, then prints, per shard, the score of that sample on its positives, and the mean score
of every sample on the negatives: the empirical FP rate of a query.

```
Query check (z=6, 10 (k+z)-mers of each shard's first sample, 10 random sequences of 1000 bases):
  idx_g0_p0: sample_0 mean 1.000, min 1.000, 10/10 perfect; negatives mean 0.0000, max 0.0001 (sample_3), expected 0.0000
  idx_g0_p1: skipped (sample file not found: /data/S5.fa.gz)
```

- **Broken index** - a shard whose positive score is not `--min-gap` above its negative score fails
  the check: its filters are empty (nothing hits) or saturated (everything hits). A shard built with
  `--ab` > 1 can miss k-mers that appear in its raw sample file, hence a gap rather than a perfect
  score.
- **Expected FP rate** - when the shard was built with `--fpr-stats` (see
  [build - Stats](build.md#stats)), `expected` is the FP rate of a query its samples' Bloom filters
  give: a position hits when its z+1 k-mers all do (`fpr^(z+1)`, averaged over the samples). An
  empirical rate more than 10 times above it (and above 0.001) is reported as suspect; it does not
  fail the check.
- A failed kmindex query fails the check.

#### Autorepair

Moving a registry, or the folders its shards link to, leaves `index.json` stale. kmindex finds a shard at `<registry>/<name>` and follows it when it is a symlink; a relative link is resolved against the current directory, not the registry. With `--autorepair`, `check` first repairs:

1. the root `path` of `index.json`, set to the registry;
2. relative links, made absolute;
3. a lost shard (missing folder or dangling link), linked to the first folder found that holds its samples, in the same order, with a complete structure: `<old path>/<name>` (the registry was moved), `<registry>/work/*/previous/<name>` (an interrupted publish), then for each `--search DIR`: `DIR/<name>`, `DIR/*/<name>` and `DIR/<name of the old link target>`. Nothing is moved or copied, and a folder holding other samples (another version) is never linked;
4. a shard found nowhere, removed from `index.json` with its dangling link, after one confirmation (skipped with the global `-Y`).

`--sh` limits 2-4 to its shards. Before any change, under the registry lock, `index.json` is copied to `index.json.<YYYYmmdd_HHMMSS>.bak`. A shard whose folder exists but fails its checks is only reported, and an index folder of the registry that is not registered is reported (`manage add` registers it). The checks then run on the repaired registry.

`apply` runs `check` before and after each publish and in the finish job: a broken shard is never
published, and a shard failing its check after the swap keeps the runs, merges and previous version
it was built from.

### `info`

| Option | Description |
|--------|-------------|
| `--sh, --shard TEXT` | Shard to show information for (required) |
| `--json` | Output as JSON |

### `remove`

| Option | Description |
|--------|-------------|
| `--sh, --shard TEXT` | Shard(s) to remove (required, repeatable) |
| `-d, --delete-files` | Also delete the shard files from disk |
| `--missing-ok` | Skip shards that are not registered instead of failing |
| `--keep-link` | Only edit `index.json`: leave a symlinked entry in place |

Each shard is removed after confirmation, skipped with the global `-Y` option.

### `rename`

```
kmhelpers manage rename OLD NEW
kmhelpers manage rename --index OLD NEW [--compose-dir COMPOSE_DIR]
```

| Argument / Option | Description |
|-------------------|-------------|
| `OLD`, `NEW` | Current and new shard name, or index name with `--index` |
| `--index` | Rename the index: every shard `OLD_g<k>[_p<j>]` becomes `NEW_g<k>[_p<j>]` |
| `--compose-dir DIR` | With `--index`: also rename `DIR/OLD/` and the shard names its `layout.yaml` records |

A shard is its folder (or symlink) `<registry>/<shard>` and its `index.json` entry. kmindex stores nothing name-specific in the folder, so `rename` renames the folder, or only the link of a symlinked shard, and the key of its entry, in place and in the same order; kmindex is not needed and no data is moved. Its logs and stats, `logs/<shard>/`, follow it (the `shard` field of `stats.yaml` too).

- Under the registry lock, `index.json` is first copied to `index.json.<YYYYmmdd_HHMMSS>.bak`, then written once. A failed rename undoes the folders already renamed.
- Refused when `NEW` is registered or exists in the registry or in `logs/`, is a reserved name (`work`, `assets`, `logs`, hidden), while a job of a build of the registry is queued or running, or while a session still has a renamed shard to publish.
- `--index` lists the renames and asks once (skipped with the global `-Y`). An index is only the prefix of its shard names: shards not named `OLD_g<k>` or `OLD_g<k>_p<j>` are not renamed.
- Without `--compose-dir`, the compose layout keeps the old names, and the next `compose -n OLD` would build new shards under them. With it, `COMPOSE_DIR/OLD/` becomes `COMPOSE_DIR/NEW/`, checked before any shard is renamed, so the next `compose -n NEW` updates the renamed shards. The sessions already composed keep the old names in their files.

### `relink`

| Option | Description |
|--------|-------------|
| `-i, --input-dir DIR` | Directory containing the moved index files (required) |
| `--sh, --shard TEXT` | Shard to relink (default: all registered shards) |

### `clean`

| Option | Description |
|--------|-------------|
| `--sh, --shard TEXT` | Clean only these shards (default: all, repeatable); fails if one is not registered |
| `--assets` | Also remove `assets/<session>/` of the finished sessions |
| `--logs` | Also remove the logs and reports of `logs/`; the stats are kept |
| `-n, --dry-run` | Only list what would be removed, with the sizes |

A published shard built from a single kmtricks run is that run moved in place, with its build intermediates. `clean` removes the folders read neither by kmindex nor by kmhelpers once the run is built: `superkmers/`, `counts/`, `minimizers/`, `partition_infos/`, `merge_infos/`, `histograms/`, `filters/` and `howde_index/`. It keeps what a query or a merge reads (`matrices/`, `hash.info`, `repartition_gatb/`, `config_gatb/`, `options.txt`, `kmtricks.fof`, `build_infos.txt`) and what the kmhelpers stats read (`run_infos.txt`, `fpr/`). The run scripts of a build already delete `superkmers/`.

- `--assets` removes the plan, scripts and progress of a session only when every shard of its plan holds its samples and no job of the plan is queued or running; the other sessions are listed as kept, with the reason. `apply --status` no longer knows a removed session.
- `--logs` removes `logs/<shard>/*.log` (and `.log.prev`), `logs/slurm/` and the `kmhelpers_*.yaml` reports. `stats.yaml` and `<run>.stats.json` stay. It is refused while a job of any session is queued or running.

Everything found is listed with its size, then removed after one confirmation, skipped with the global `-Y` option.

## Examples

```bash
# Create a registry in the current directory
kmhelpers manage create

# Create a registry and register indices from a directory
kmhelpers manage create -i /data/indices

# List all registered shards
kmhelpers manage list
kmhelpers manage -r /path/to/registry list

# Add indices from a directory to an existing registry
kmhelpers manage add -i /data/new_indices

# Show info for a shard
kmhelpers manage info --sh my_index

# Show info as JSON
kmhelpers manage info --sh my_index --json

# Check consistency (structure, then a query of each shard's first sample)
kmhelpers manage check

# Structure only
kmhelpers manage check --nq

# Require a wider gap between positive and negative scores
kmhelpers manage check --min-gap 0.8

# Repair a moved registry, looking for lost shards in /data/indices
kmhelpers manage check --autorepair --search /data/indices

# Remove a shard (keep files)
kmhelpers manage remove --sh my_index

# Remove a shard and delete its files from disk
kmhelpers manage remove --sh my_index -d

# Remove several shards without confirmation
kmhelpers -Y manage remove --sh idx1 --sh idx2

# Rename a shard
kmhelpers manage rename idx_g0 virus_g0

# Rename an index: all its shards, and its compose folder and layout
kmhelpers -Y manage rename --index idx virus --compose-dir db/compose

# Relink all shards from a new directory
kmhelpers manage relink -i /new/location

# Relink one shard
kmhelpers manage relink -i /new/location --sh my_index

# List what clean would remove, then remove it, with the finished sessions and the logs
kmhelpers manage clean -n --assets --logs
kmhelpers -Y manage clean --assets --logs
```