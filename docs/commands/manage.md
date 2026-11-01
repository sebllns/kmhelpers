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
    **Output:** updated registry state (create, add, remove, rename, relink) or printed info (list, info, check)

## Subcommands

| Subcommand | Description |
|------------|-------------|
| `create` | Initialise a registry and optionally register existing indices |
| `add` | Register existing kmtricks indices in an existing registry |
| `list` | List all indices in a registry |
| `info` | Show detailed information about an index |
| `check` | Validate registry consistency and index structures |
| `remove` | Remove one or more indices from the registry |
| `rename` | Rename an index |
| `relink` | Recreate links after moving index files |

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
| `-d, --delete-files` | Also delete index files from disk |
| `--missing-ok` | Skip index IDs that are not registered instead of failing |
| `--keep-link` | Only edit `index.json`: leave a symlinked entry in place |

Each shard is removed after confirmation, skipped with the global `-Y` option.

### `rename`

```
kmhelpers manage rename INDEX_ID NEW_INDEX_ID
```

| Argument | Description |
|----------|-------------|
| `INDEX_ID` | Current index ID |
| `NEW_INDEX_ID` | New index ID |

### `relink`

| Option | Description |
|--------|-------------|
| `-i, --input-dir DIR` | Directory containing the moved index files (required) |
| `--sh, --shard TEXT` | Shard to relink (default: all registered shards) |

## Examples

```bash
# Create a registry in the current directory
kmhelpers manage create

# Create a registry and register indices from a directory
kmhelpers manage create -i /data/indices

# List all registered indices
kmhelpers manage list
kmhelpers manage -r /path/to/registry list

# Add indices from a directory to an existing registry
kmhelpers manage add -i /data/new_indices

# Show info for a specific index
kmhelpers manage info --sh my_index

# Show info as JSON
kmhelpers manage info --sh my_index --json

# Check consistency (structure, then a query of each shard's first sample)
kmhelpers manage check

# Structure only
kmhelpers manage check --nq

# Require a wider gap between positive and negative scores
kmhelpers manage check --min-gap 0.8

# Remove an index (keep files)
kmhelpers manage remove --sh my_index

# Remove an index and delete files from disk
kmhelpers manage remove --sh my_index -d

# Remove multiple indices without confirmation
kmhelpers -Y manage remove --sh idx1 --sh idx2

# Rename an index
kmhelpers manage rename old_name new_name

# Relink all indices from a new directory
kmhelpers manage relink -i /new/location

# Relink a specific index
kmhelpers manage relink -i /new/location --sh my_index
```