# Installation

## Requirements

- Python 3.10 or later, on Linux or macOS (x86_64 or arm64)
- External tools, called by `kmhelpers`:

| Tool | Version | Role |
|---|---|---|
| [kmindex](https://github.com/tlemane/kmindex) | ≥ 0.6.1 | builds and queries the indexes |
| [kmtricks](https://github.com/tlemane/kmtricks) | ≥ 1.6.0 | counts k-mers, run by `kmindex` |
| [ntCard](https://github.com/bcgsc/ntCard) | ≥ 1.2.2 | estimates the number of k-mers of each sample |

The pip and Bioconda installs below provide these tools. To use other versions, see [Custom tool versions](#custom-tool-versions).

All `conda` commands require [Conda](https://docs.conda.io/projects/conda/en/latest/user-guide/install/index.html) (Miniconda or Miniforge, for instance).

## With pip (PyPI)

```bash
python -m venv ~/.kmhelpers
source ~/.kmhelpers/bin/activate
pip install kmhelpers
kmhelpers install-deps
```
!!! note
    [`install-deps`](../commands/install-deps.md) downloads prebuilt `kmtricks`, `kmindex` and `ntcard` binaries next to the `kmhelpers` executable, here `~/.kmhelpers/bin`, so they are in `PATH` whenever the environment is active. A virtual environment keeps them apart from the rest of the system. The architecture should be detected from the current machine; `--target x86_64` or `--target arm64` selects another one.

To update:

```bash
pip install --upgrade kmhelpers
```

## With Conda (Bioconda)

```bash
conda create -n kmhelpers -c conda-forge -c bioconda kmhelpers
conda activate kmhelpers
```

`kmindex` (with `kmtricks`) and `ntcard` are installed as dependencies.

To update:

```bash
conda update -n kmhelpers -c conda-forge -c bioconda kmhelpers
```

!!! note
    A new release reaches Bioconda a few hours to a few days after PyPI.

## From source

### 1. Clone the repository

<!-- release-only -->
```bash
git clone --branch v@VERSION@ https://github.com/sebllns/kmhelpers
cd kmhelpers
```
<!-- /release-only -->
<!-- dev-only -->
```bash
git clone https://github.com/sebllns/kmhelpers
cd kmhelpers
```

This is the development version. To install a release, use the documentation
of that version (version selector at the top of the page).
<!-- /dev-only -->

### 2. Create and activate the Conda environment

```bash
conda env create -f conda/environment.yml -p ./.env
conda activate ./.env
```

This installs `kmindex`, `ntcard` and the Python dependencies into `.env`, and `kmhelpers` itself in editable mode, so changes to the source take effect without reinstalling.

!!! note
    Activate the environment in each new terminal session before using `kmhelpers`. It can also be created in a permanent location, for example `-p ~/.kmhelpers`.

### Update

From the repository root:

<!-- release-only -->
```bash
git fetch --tags
git checkout v@VERSION@
conda env update -f conda/environment.yml -p ./.env --prune
```
<!-- /release-only -->
<!-- dev-only -->
```bash
git pull origin main
conda env update -f conda/environment.yml -p ./.env --prune
```
<!-- /dev-only -->

## Verify the installation

```bash
kmhelpers --version
kmhelpers check-deps
```

[`check-deps`](../commands/check-deps.md) prints the version and path of each tool, or a warning for a tool it cannot find. `kh` is a short alias for `kmhelpers`.

## Custom tool versions

`kmhelpers` looks for each tool:

1. in the directory given by `<TOOL>_BIN_PATH` (`KMINDEX_BIN_PATH`, `KMTRICKS_BIN_PATH`, `NTCARD_BIN_PATH`), if set
2. then in `PATH`

`kmindex` itself runs `kmtricks` from `PATH`, so keep both in a directory that is in `PATH`, or in the same directory.

### With install-deps

Each version option takes a release of the tool (`0` skips it): `--kmindex` and `--kmtricks` take a version from the [kmindex](https://github.com/tlemane/kmindex/releases) and [kmtricks](https://github.com/tlemane/kmtricks/releases) releases, without the leading `v`, and `--ntcard` a tag from the [portable ntCard builds](https://github.com/sebllns/ntCard/releases).

```bash
# Replace kmindex next to kmhelpers, keep the other tools
kmhelpers install-deps --kmindex 0.6.1 --kmtricks 0 --ntcard 0

# Install all tools into a separate directory
kmhelpers install-deps --path ~/kmh_tools
export PATH=~/kmh_tools:$PATH
```

### From source, or another package manager

Build or install the tool following its own instructions ([kmindex](https://github.com/tlemane/kmindex), [kmtricks](https://github.com/tlemane/kmtricks), [ntCard](https://github.com/bcgsc/ntCard)), then make its binary directory visible to `kmhelpers`:

```bash
# Example for kmindex

# --> EASIEST <-- Add the directory to PATH 
export PATH=/path/to/kmindex/bin:$PATH

# OR

# For kmhelpers ONLY: set the variable of that tool
export KMINDEX_BIN_PATH=/path/to/kmindex/bin
```
!!! note
    Add the `export` line to `~/.bashrc` (or the profile of your shell) to keep it across sessions. In a Conda environment, a tool version can also be pinned directly, for example `conda install -c conda-forge -c bioconda kmindex=0.6.1`.

Run `kmhelpers check-deps` to confirm which binary and version are used.
