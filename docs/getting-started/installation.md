# Installation

## Prerequisites

- [Conda](https://docs.conda.io/projects/conda/en/latest/user-guide/install/index.html) (Miniconda or Anaconda for instance)

## Quick Install

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

### 2. Create the Conda environment

```bash
conda env create -f conda/environment.yml -p ./.env
```

This installs `kmindex`, `ntcard`, and all Python dependencies into a local `.env` directory.

### 3. Activate the environment

```bash
conda activate ./.env
```

!!! note
    Run this activation command each time you open a new terminal session before using `kmhelpers`.

!!! tip
    You can install to a permanent location instead:

    ```bash
    conda env create -f conda/environment.yml -p ~/.kmhelpers
    conda activate ~/.kmhelpers
    ```

### 4. Verify

```bash
kmhelpers --version
kmhelpers --help
```

Verify dependencies:

```bash
kmindex --version
kmtricks --version
ntcard --version
```

## Updating

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

Then verify the installed version:

```bash
kmhelpers --version
```
