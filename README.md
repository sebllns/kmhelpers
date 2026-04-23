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
git clone https://gitlab.inria.fr/omicfinder/kmhelpers --branch v0.6.2
cd kmhelpers
```

### Quick Install with Conda 

```bash
# Create environment with kmindex pre-installed
conda env create -f conda/environment.yml -p .env

# Activate the environment
# Run this each time you open a new terminal session before using kmhelpers
conda activate ./.env
```

> **Note:** Each time you open a new terminal, navigate to the `kmhelpers` directory and activate the environment before running any `kmhelpers` commands:
> ```bash
> cd /path/to/kmhelpers
> conda activate ./.env
> ```

This will automatically:
- Install [`kmindex`](https://github.com/tlemane/kmindex) and [`ntcard`](https://github.com/BirolLab/ntCard) from bioconda
- Install `kmhelpers` Python package

**Prerequisites:** Conda (Miniconda or Anaconda) must be installed. If you don't have it, see [Installation Instructions](https://docs.conda.io/projects/conda/en/latest/user-guide/install/index.html).

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
git pull origin dev/v0.6.2
git pull origin feature/my-feature
```

If your local branch is already tracking a remote branch, you can simply run:

```bash
git pull
```

Check the installed version:

```bash
kmhelpers --version
```bash

## License

This project is licensed under the GNU General Public License - see the [LICENSE](LICENSE) file for details.

Copyright (c) 2026 Sébastien Bellenous, Genscale, INRIA

## Contact

For questions, bug reports, or contributions, please contact:

- **Author**: [Sébastien BELLENOUS](https://github.com/sebllns)
- **Email**: kmhelpers@groupes.renater.fr
- **Repository**: [GitLab](https://gitlab.inria.fr/omicfinder/kmhelpers)
- **Supervisor**: [Pierre Peterlongo](https://github.com/pierrepeterlongo)

---

**Version**: 0.6.2
**Status**: Development

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for detailed version history.
