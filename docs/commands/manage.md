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

After the structure checks, `check` takes 10 random (k+z)-mers from the first sample of each shard
(from the sample file listed first in the shard's `kmtricks.fof`) and queries them all in one
kmindex query against the registry. It then prints that sample's score on its own (k+z)-mers:

```
Query check (z=6, 10 (k+z)-mers of each shard's first sample):
  idx_g0_p0: sample_0 mean 1.000, min 1.000, 10/10 perfect
  idx_g0_p1: skipped (sample file not found: /data/S5.fa.gz)
```

The score is only reported. A shard built with `--ab` > 1 can miss k-mers that appear in its raw
sample file. A failed kmindex query fails the check. `apply` runs `check` after each publish and in
the finish job, so the query check runs there too.

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
| `-y, --yes` | Skip confirmation prompt |
| `--missing-ok` | Skip index IDs that are not registered instead of failing |
| `--keep-link` | Only edit `index.json`: leave a symlinked entry in place |

### `rename`

| Option | Description |
|--------|-------------|
| `-f, --from TEXT` | Current index ID (required) |
| `-t, --to TEXT` | New index ID (required) |

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

# Remove an index (keep files)
kmhelpers manage remove --sh my_index

# Remove an index and delete files from disk
kmhelpers manage remove --sh my_index -d

# Remove multiple indices without confirmation
kmhelpers manage remove --sh idx1 --sh idx2 -y

# Rename an index
kmhelpers manage rename -f old_name -t new_name

# Relink all indices from a new directory
kmhelpers manage relink -i /new/location

# Relink a specific index
kmhelpers manage relink -i /new/location --sh my_index
```