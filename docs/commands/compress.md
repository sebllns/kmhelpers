# compress

## Synopsis

Compress the shards of a registry.

!!! abstract "USAGE"
    ```
    kmhelpers compress [OPTIONS]
    ```

    | Argument | Description |
    |----------|-------------|
    | `-r, --registry-path DIR` | Path to kmindex registry (required) |
    | `--sh, --shard PATTERN` | Shards to compress, as names or glob patterns, repeatable or comma-separated (default: all) |

!!! abstract "I/O"
    **Input:** kmindex registry (`-r`), shards (`--shard`, default: all)  
    **Output:** compressed shards in place within the registry

## Advanced Options
| Option | Description |
|--------|-------------|
| `--block-size INT` | Size of uncompressed blocks in MB (default: 8) |
| `--cpr-level INT` | Compression level 1–22 (default: 3) |
| `--reorder` | Enable column reordering before compression |
| `-s, --sampling INT` | Number of rows to sample for column reordering (default: 20000) |
| `--column-per-block INT` | Reorder columns in groups of N (0 = all columns, must be multiple of 8; default: 0) |
| `-t, --threads INT` | Number of threads (default: 14) |
| `--delete` | Delete the uncompressed matrices after successful compression |
| `--check` | Check query results after compression |

## Description

Compresses each selected shard with `kmindex compress`, one after the other. Without `--shard`, every shard of the registry is compressed. A pattern that matches no shard is a warning; the command fails only if no shard matches. A failed shard does not stop the others: the command fails at the end and lists them.

**Column reordering** - use `--reorder` to reorder columns before compression, which can improve compression ratio. Use `--sampling` to control how many rows are sampled to determine the optimal column order.

**Deletion** - use `--delete` to remove the uncompressed matrices after successful compression. Requires confirmation unless `-Y` is passed at the root level.

## Examples

```bash
# Compress every shard of the registry
kmhelpers compress -r ./registry

# Compress the shards of one group
kmhelpers compress -r ./registry --sh 'my_index_g0_*'

# With column reordering
kmhelpers compress -r ./registry --sh my_index --reorder -s 50000

# Custom compression level with multiple threads
kmhelpers compress -r ./registry --sh my_index --cpr-level 6 -t 16

# Delete uncompressed index after compression
kmhelpers compress -r ./registry --sh my_index --delete
```