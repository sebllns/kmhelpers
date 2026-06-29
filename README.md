# kmhelpers

---

<img src="assets/kmhelpers-logo-v1.png" alt="Kmhelpers Logo" width="64" height="64">

A Python toolkit for managing, compressing, and querying [kmindex](https://github.com/tlemane/kmindex) indices efficiently.

---

## Table of Contents

- [Getting Started](#getting-started)
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

```bash
bash scripts/setup.sh
```

This installs `kmtricks` and `kmindex` directly into the `.env` environment. The source tree is removed after a successful build.

### Verify Installation

Once the environment has been activated:

```bash
# Check the installed version
kmhelpers --version

# View available commands
kmhelpers --help
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
