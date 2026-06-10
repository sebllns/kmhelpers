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
kmhelpers fof create -d /data/sequences -o samples.fof

# Create FOF with recursive search
kmhelpers fof create -d /data/sequences -o samples.fof --recursive

# Add a sample
kmhelpers fof add --fof samples.fof -s /data/sample.fa

# Add a sample with a custom ID
kmhelpers fof add --fof samples.fof -s /data/sample.fa -n my_sample

# List samples
kmhelpers fof list samples.fof

# List samples with full paths
kmhelpers fof list samples.fof --show-paths

# Validate
kmhelpers fof validate samples.fof
```

---

## fof create

| Option | Description |
|--------|-------------|
| `-d, --from-directory DIR` | Directory containing FASTA/FASTQ files (required) |
| `-o, --output FILE` | Output FOF file path (required) |
| `--recursive` | Search subdirectories recursively |
| `-x, --extensions TEXT` | File extensions to include (repeatable, default: common bioinformatics formats) |
| `-v, --verbose` | Show detailed output |

## fof add

| Option | Description |
|--------|-------------|
| `--fof FILE` | FOF file to modify (required) |
| `-s, --sample-file FILE` | Sample file to add (required) |
| `-n, --sample-id TEXT` | Sample ID (auto-extracted from filename if not provided) |

## fof list

| Argument/Option | Description |
|-----------------|-------------|
| `FOF_FILE` | FOF file to list (required) |
| `--show-paths` | Show full file paths |
| `--json` | Output as JSON |

## fof validate

| Argument/Option | Description |
|-----------------|-------------|
| `FOF_FILE` | FOF file to validate (required) |
| `-v, --verbose` | Show detailed validation output |
