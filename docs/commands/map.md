# map

## Synopsis

Show the state of the indices in a build directory: which sessions built each index, which version is active, and, given the compose directory, which declared indices are still missing.

!!! abstract "USAGE"
    ```
    kmhelpers map [OPTIONS] BUILD_DIR
    ```

    | Argument | Description |
    |----------|-------------|
    | `BUILD_DIR` | Index directory, the `-o` of [`build`](build.md) (required) |
    | `-c, --compose-dir COMPOSE_DIR` | Directory holding the `NAME/SESSION/NAME.yaml` index definitions |
    | `-o, --output FILE` | Write the map as an image, format taken from the extension (`.svg`, `.png`, `.pdf`) |
    | `--json` | Print the collected map as JSON instead of a table |

!!! abstract "I/O"
    **Input:** `BUILD_DIR`, optionally `COMPOSE_DIR`  
    **Output:** table on stdout, optional image (`-o`)

See [build - Paths](build.md#paths) for the directory layout.

## Description

`map` is read-only. It draws a grid with one row per index name and one column per session:

- **Build side:** every folder `BUILD_DIR/kmindex_data/SESSION/NAME/` is a built index. The version registered in `BUILD_DIR/index.json` (through the `BUILD_DIR/NAME` link) is the active one.
- **Compose side** (`-c`): every span registry `COMPOSE_DIR/NAME/SESSION/NAME.yaml` declares the indices of that session.

| Status | Meaning |
|--------|---------|
| `active` | Built, currently registered version |
| `superseded` | Built, replaced by a later session (kept on disk after an update) |
| `missing` | Declared in `COMPOSE_DIR`, not built |
| `orphan` | Built, not declared in `COMPOSE_DIR` (requires `-c`) |
| `broken` | Registered, but its data folder is missing |

Sessions are ordered by creation time. Indices whose data lives outside `BUILD_DIR/kmindex_data` are shown in an `(external)` column.

The table shows the status and sample count of each cell. The image (`-o`) and JSON output also give the k-mer size, partition count, matrix size on disk, and compression state (`C` compressed, `U` uncompressed, `C+U` both).

## Examples

```bash
# Build side only
kmhelpers map coli_build

# Compare with the definitions and write an image
kmhelpers map coli_build -c coli_db/compose -o coli_map.svg
```
