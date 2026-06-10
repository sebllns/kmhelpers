# registry

Manage k-mer index registries.

## Usage

```
kmhelpers registry [OPTIONS] COMMAND [ARGS]...
```

## Options

| Option | Description |
|--------|-------------|
| `-r, --registry-path DIR` | Path to kmindex registry (default: current directory) |

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

## Examples

```bash
# Create a registry in the current directory
kmhelpers registry create

# Create a registry and register indices from a directory
kmhelpers registry create -i /data/indices

# List all registered indices
kmhelpers registry list
kmhelpers registry -r /path/to/registry list

# Add indices from a directory to an existing registry
kmhelpers registry add -i /data/new_indices

# Show info for a specific index
kmhelpers registry info -n my_index

# Show info as JSON
kmhelpers registry info -n my_index --json

# Check consistency
kmhelpers registry check

# Remove an index (keep files)
kmhelpers registry remove -n my_index

# Remove an index and delete files from disk
kmhelpers registry remove -n my_index -d

# Remove multiple indices without confirmation
kmhelpers registry remove -n idx1 -n idx2 -y

# Rename an index
kmhelpers registry rename -f old_name -t new_name

# Relink all indices from a new directory
kmhelpers registry relink -i /new/location

# Relink a specific index
kmhelpers registry relink -i /new/location -n my_index
```
