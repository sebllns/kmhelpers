# compress

Compress an index managed in a registry.

## Usage

```
kmhelpers compress [OPTIONS]
```

## Description

Registry-based compression using the KmindexWrapper. Provides a simpler interface for compressing indices managed in a registry compared to using `kmindex` directly.

## Examples

```bash
# Basic compression
kmhelpers compress -r ./registry -n my_index

# With column reordering
kmhelpers compress -r ./registry -n my_index --reorder -s 50000

# Custom compression level with multiple threads
kmhelpers compress -r ./registry -n my_index --cpr-level 6 -t 16
```

## Options

| Option | Description |
|--------|-------------|
| `-r, --registry-path DIR` | Path to kmindex registry (required) |
| `-n, --index-name TEXT` | Name of the index to compress (required) |
| `--block-size INT` | Size of uncompressed blocks in MB |
| `--cpr-level INT` | Compression level |
| `--reorder` | Reorder columns before compression |
| `-s, --save-period INT` | Save period for column reordering |
| `-t, --threads INT` | Number of threads |
