# Installation

## Prerequisites

- [Conda](https://docs.conda.io/projects/conda/en/latest/user-guide/install/index.html) (Miniconda or Anaconda for instance)

## Quick Install

### 1. Clone the repository

```bash
git clone https://github.com/sebllns/kmhelpers
cd kmhelpers
```

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

```bash
git pull origin main
```

To pull from a specific branch:

```bash
git pull origin dev/v0.6.3
```

Then verify the installed version:

```bash
kmhelpers --version
```


