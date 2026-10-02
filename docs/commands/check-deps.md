# check-deps

## Synopsis

Check that `kmindex`, `kmtricks` and `ntcard` are callable.

!!! abstract "USAGE"
    ```
    kmhelpers check-deps
    ```

## Description

For each tool, `check-deps` resolves its path and runs `<tool> --version`, then logs the version and path. A warning is logged for each tool that cannot be found.

A `<TOOL>_BIN_PATH` environment variable (e.g. `KMINDEX_BIN_PATH`) is prepended to `PATH` before the lookup.

## Example

```
$ kmhelpers -NF check-deps
INFO     | kmindex    kmindex v0.6.1       /opt/kmhelpers/.env/bin/kmindex
INFO     | kmtricks   kmtricks v1.6.0      /opt/kmhelpers/.env/bin/kmtricks
WARNING  | ntcard     ntcard not found. Either add its installation directory to PATH, or set the NTCARD_BIN_PATH environment variable to that directory.
```

Missing tools can be installed with [`install-deps`](install-deps.md) (kmtricks and kmindex only).
