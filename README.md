# kmhelpers

---

<img src="assets/kmhelpers-logo-v1.png" alt="Kmhelpers Logo" width="64" height="64">

A Python toolkit for managing, compressing, and querying [kmindex](https://github.com/tlemane/kmindex) indices efficiently.

**Documentation:** <https://sebllns.github.io/kmhelpers/>

---

## Table of Contents

- [Getting Started](#getting-started)
- [Documentation](https://sebllns.github.io/kmhelpers/)
- [Update](#update)
- [License](#license)
- [Contact](#contact)
- [Changelog](#changelog)


## Getting started

### Clone the repository and navigate to it

```bash
git clone https://github.com/sebllns/kmhelpers
git checkout dev/v0.6.3
cd kmhelpers
```

### Quick Install with Conda 

This will automatically:
- Install `kmhelpers` Python package

**Prerequisites:** Conda (Miniconda or Anaconda) must be installed. If you don't have it, see [Installation Instructions](https://docs.conda.io/projects/conda/en/latest/user-guide/install/index.html).

```bash
# Create environment with kmindex pre-installed
conda env create -f conda/environment.yml -p ./.env

# Activate the environment
# Run this each time you open a new terminal session before using kmhelpers
conda activate ./.env
```

> **Note:** Once per terminal session, activate the environment before using `kmhelpers`:
> ```bash
> conda activate /path/to/kmhelpers/.env
> ```
> `.env` can be replaced by any path, for example a shared or permanent location like `~/.kmhelpers`:
> ```bash
> conda env create -f conda/environment.yml -p ~/.kmhelpers
> conda activate ~/.kmhelpers
> ```

### Install `kmindex`

`kmhelpers` relies on a feature of `kmindex` — the `static_repart` index type — that is not yet available in the official conda package. Until an official release includes it, `kmindex` (and its dependency `kmtricks`) must be built from source.

#### Supported platforms

`scripts/setup.sh` automates the full build and is tested on the following platforms:

| OS | Architecture | Status |
|---|---|---|
| Linux | x86\_64 | Supported |
| macOS | x86\_64 (Intel) | Supported |
| macOS | arm64 (Apple Silicon) | Supported |


```bash
bash scripts/setup.sh
```

This installs `kmtricks` and `kmindex` directly into the `.env` environment. The source tree is removed after a successful build.

#### Manual build

If `setup.sh` fails or your platform is not listed above, you can build manually. Requirements: a C++17 compiler, `cmake = 3.24`, `git`, and the libraries in `conda/build_kmindex_<platform>.yml`.

> **Note:** `$CONDA_PREFIX` points to the active conda environment. Make sure the environment is activated before running these commands.

```bash
# 1. Clone kmindex and switch kmtricks to static_repart
git clone --depth 1 --branch next-dev --recurse-submodules \
  https://github.com/tlemane/kmindex .build/kmindex
git -C .build/kmindex/thirdparty/kmtricks fetch --depth 1 origin static_repart
git -C .build/kmindex/thirdparty/kmtricks checkout FETCH_HEAD

# 2. Build and install kmtricks
mkdir -p .build/kmindex/thirdparty/kmtricks/kmbuild
cd .build/kmindex/thirdparty/kmtricks/kmbuild
cmake .. -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX="$CONDA_PREFIX" \
  -DCMAKE_PREFIX_PATH="$CONDA_PREFIX" \
  -DWITH_MODULES=OFF -DWITH_SOCKS=OFF -DWITH_HOWDE=OFF \
  -DCOMPILE_TESTS=OFF -DSTATIC=OFF -DWITH_PLUGIN=OFF \
  "-DKMER_LIST=32 64 96 128" -DMAX_C=4294967295
make -j"$(nproc 2>/dev/null || sysctl -n hw.logicalcpu)"
cp ../bin/kmtricks "$CONDA_PREFIX/bin/"

# 3. Build and install kmindex
cd -
mkdir -p .build/kmindex/kmbuild
cd .build/kmindex/kmbuild
cmake .. -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX="$CONDA_PREFIX" \
  -DCMAKE_PREFIX_PATH="$CONDA_PREFIX" \
  -DWITH_TESTS=OFF -DWITH_SERVER=OFF \
  -DCMAKE_CXX_STANDARD=17 -DMAX_KMER_SIZE=256 -DSPDLOG_HEADER_ONLY=ON
make -j"$(nproc 2>/dev/null || sysctl -n hw.logicalcpu)"
make install
```

### Verify Installation

Once the environment has been activated:

```bash
# Check the installed version
kmhelpers --version

# View available commands
kmhelpers --help
```

> **Tip:** `kh` is available as a short alias for `kmhelpers` (e.g. `kh --help`).

```bash

# Check ntcard
ntcard --version

# Check kmtricks
kmtricks --version

# Check kmindex
kmindex --version
```

### Update

To pull the latest changes from the default branch (`main`):

```bash
git pull origin main
```

To pull from a specific branch (e.g., a development or release branch):

```bash
git pull origin <branch-name>

# Examples
git pull origin dev/v0.6.3
git pull origin feature/my-feature
```

If your local branch is already tracking a remote branch, you can simply run:

```bash
git pull
```

Check the installed version:

```bash
kmhelpers --version
```

## License

This project is licensed under the GNU General Public License - see the [LICENSE](LICENSE) file for details.

Copyright (c) 2026 Sébastien Bellenous, Genscale, INRIA

## Contact

For questions, bug reports, or contributions, please contact:

- **Author**: [Sébastien BELLENOUS](https://github.com/sebllns)
- **Email**: kmhelpers@groupes.renater.fr
- **Repository**: [GitHub](https://github.com/sebllns/kmhelpers)
- **Supervisor**: [Pierre Peterlongo](https://github.com/pierrepeterlongo)

---

**Version**: 0.6.3
**Status**: Development

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for detailed version history.


# Acknowledgements

The authors thank Téo Lemane for developing `kmindex` and for his
responsiveness in addressing feature requests and issues raised during the
development of `kmhelpers`. We acknowledge the GenOuest core facility
(<https://www.genouest.org>) for providing the computing infrastructure.
The work was funded by the Inria Challenge "OmicFinder"
(<https://project.inria.fr/omicfinder/>), and by the state funding managed by the French National Research Agency under the France 2030 program [ANR-22-PEAE-0005].
