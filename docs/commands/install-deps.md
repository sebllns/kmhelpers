# install-deps

## Synopsis

Download and install `kmtricks`, `kmindex` and `ntcard` prebuilt binaries from their GitHub releases.

!!! abstract "USAGE"
    ```
    kmhelpers install-deps [OPTIONS]
    ```

!!! abstract "I/O"
    **Input:** none (downloads from github.com/tlemane/kmtricks, github.com/tlemane/kmindex and github.com/sebllns/ntCard)  
    **Output:** `kmtricks`, `kmindex`, `kmindex-server` and `ntcard` binaries in the installation directory

## Options
| Option | Description |
|--------|-------------|
| `--kmtricks VERSION` | kmtricks version to install, `0` to skip (default: `1.6.0`) |
| `--kmindex VERSION` | kmindex version to install, `0` to skip (default: `0.6.1`) |
| `--ntcard VERSION` | ntcard release tag to install, `0` to skip (default: `1.2.2-portable1`) |
| `--target [x86_64\|arm64]` | Target architecture (default: detected from the current machine) |
| `--path DIR` | Installation directory (default: directory of the `kmhelpers` executable) |

## Description

The operating system (Linux or macOS) is detected automatically. Existing binaries with the same name are overwritten after confirmation (skipped with the global `-y` option). A warning is logged if the installation directory is not in `PATH`.

`ntcard` comes from [sebllns/ntCard](https://github.com/sebllns/ntCard), a fork of ntCard that publishes portable builds: fully static on Linux, and depending only on the system library on macOS. The download is verified against the `SHA256SUMS` file of the release.

## Examples

```bash
# Install default versions next to kmhelpers
kmhelpers install-deps

# Install only kmindex 0.6.1 into a custom directory
kmhelpers -y install-deps --kmtricks 0 --kmindex 0.6.1 --path ~/bin
```
