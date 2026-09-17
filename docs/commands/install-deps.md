# install-deps

## Synopsis

Download and install `kmtricks` and `kmindex` prebuilt binaries from their GitHub releases.

!!! abstract "USAGE"
    ```
    kmhelpers install-deps [OPTIONS]
    ```

!!! abstract "I/O"
    **Input:** none (downloads from github.com/tlemane/kmtricks and github.com/tlemane/kmindex)  
    **Output:** `kmtricks`, `kmindex` and `kmindex-server` binaries in the installation directory

## Options
| Option | Description |
|--------|-------------|
| `--kmtricks VERSION` | kmtricks version to install, `0` to skip (default: `1.6.0`) |
| `--kmindex VERSION` | kmindex version to install, `0` to skip (default: `0.6.1`) |
| `--target [x86_64\|arm64]` | Target architecture (default: detected from the current machine) |
| `--path DIR` | Installation directory (default: directory of the `kmhelpers` executable) |

## Description

The operating system (Linux or macOS) is detected automatically. Existing binaries with the same name are overwritten after confirmation (skipped with the global `-y` option). A warning is logged if the installation directory is not in `PATH`.

## Examples

```bash
# Install default versions next to kmhelpers
kmhelpers install-deps

# Install only kmindex 0.6.1 into a custom directory
kmhelpers -y install-deps --kmtricks 0 --kmindex 0.6.1 --path ~/bin
```
