# fof

Manage File-of-Files (FOF) for index building.

## Usage

```
kmhelpers fof COMMAND [ARGS]...
```

## Subcommands

| Subcommand | Description |
|------------|-------------|
| `create` | Create a FOF file from a directory of sequence files |
| `add` | Add a sample to an existing FOF file |
| `list` | List all samples in a FOF file |
| `validate` | Validate FOF file format and check sample files exist |

## Examples

```bash
# Create FOF from a directory
kmhelpers fof create -i /data/sequences -o samples.fof

# Add a sample
kmhelpers fof add -f samples.fof -n my_sample /data/sample.fa

# List samples
kmhelpers fof list -f samples.fof

# Validate
kmhelpers fof validate -f samples.fof
```