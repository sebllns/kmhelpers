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
| `-n, --index-ids TEXT` | Specific index IDs to register (default: all found) |

### `add`

| Option | Description |
|--------|-------------|
| `-i, --input-dir DIR` | Directory containing kmtricks indices to add (required) |
| `-n, --index-ids TEXT` | Specific index IDs to register (default: all found) |

### `info`

| Option | Description |
|--------|-------------|
| `-n, --index-id TEXT` | Index ID to show information for (required) |
| `--json` | Output as JSON |

### `remove`

| Option | Description |
|--------|-------------|
| `-n, --index-ids TEXT` | Index ID(s) to remove (required, repeatable) |
| `-d, --delete-files` | Also delete index files from disk |
| `-y, --yes` | Skip confirmation prompt |

### `rename`

| Option | Description |
|--------|-------------|
| `-f, --from TEXT` | Current index ID (required) |
| `-t, --to TEXT` | New index ID (required) |

### `relink`

| Option | Description |
|--------|-------------|
| `-i, --input-dir DIR` | Directory containing the moved index files (required) |
| `-n, --index-id TEXT` | Index ID to relink (default: all registered indices) |

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
kmhelpers manage info -n my_index

# Show info as JSON
kmhelpers manage info -n my_index --json

# Check consistency
kmhelpers manage check

# Remove an index (keep files)
kmhelpers manage remove -n my_index

# Remove an index and delete files from disk
kmhelpers manage remove -n my_index -d

# Remove multiple indices without confirmation
kmhelpers manage remove -n idx1 -n idx2 -y

# Rename an index
kmhelpers manage rename -f old_name -t new_name

# Relink all indices from a new directory
kmhelpers manage relink -i /new/location

# Relink a specific index
kmhelpers manage relink -i /new/location -n my_index
```