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
| `create` | Initialise a new registry |
| `add` | Register existing kmtricks indices |
| `list` | List all indices in a registry |
| `info` | Show detailed information about an index |
| `check` | Validate registry consistency and index structures |
| `remove` | Remove an index from the registry (optionally delete files) |
| `rename` | Rename an index |
| `relink` | Recreate links after moving files |

## Examples

```bash
# Create a registry in the current directory
kmhelpers registry create

# List all registered indices
kmhelpers registry list
kmhelpers registry -r /path/to/registry list

# Show info for a specific index
kmhelpers registry info -n my_index

# Check consistency
kmhelpers registry check

# Remove an index (keep files)
kmhelpers registry remove -n my_index

# Remove an index and delete files
kmhelpers registry remove -n my_index --delete

# Remove multiple indices without confirmation
kmhelpers registry remove -n idx1 -n idx2 -y

# Relink after moving files
kmhelpers registry relink -n my_index --new-path /new/location
kmhelpers registry relink --all
```