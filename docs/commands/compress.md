# compress

## Synopsis

Compress an index managed in a registry.

!!! abstract "USAGE"
    ```
    kmhelpers compress [OPTIONS]
    ```

    | Argument | Description |
    |----------|-------------|
    | `-r, --registry-path DIR` | Path to kmindex registry (required) |
    | `-n, --index-name TEXT` | Name of the index to compress (required) |

!!! abstract "I/O"
    **Input:** kmindex registry (`-r`), index name (`-n`)  
    **Output:** compressed index in place within the registry

## Advanced Options
| Option | Description |
|--------|-------------|
| `--block-size INT` | Size of uncompressed blocks in MB (default: 8) |
| `--cpr-level INT` | Compression level 1–22 (default: 3) |
| `--reorder` | Enable column reordering before compression |
| `-s, --sampling INT` | Number of rows to sample for column reordering (default: 20000) |
| `--column-per-block INT` | Reorder columns in groups of N (0 = all columns, must be multiple of 8; default: 0) |
| `-t, --threads INT` | Number of threads (default: 14) |
| `--delete` | Delete uncompressed index after successful compression |
| `--check` | Check query results after compression |

## Description

Registry-based compression using the KmindexWrapper. Provides a simpler interface for compressing indices managed in a registry compared to using `kmindex` directly.

**Column reordering** — use `--reorder` to reorder columns before compression, which can improve compression ratio. Use `--sampling` to control how many rows are sampled to determine the optimal column order.

**Deletion** — use `--delete` to remove the uncompressed index after successful compression. Requires confirmation unless `-y` is passed at the root level.

## Examples

```bash
# Basic compression
kmhelpers compress -r ./registry -n my_index

# With column reordering
kmhelpers compress -r ./registry -n my_index --reorder -s 50000

# Custom compression level with multiple threads
kmhelpers compress -r ./registry -n my_index --cpr-level 6 -t 16

# Delete uncompressed index after compression
kmhelpers compress -r ./registry -n my_index --delete
```