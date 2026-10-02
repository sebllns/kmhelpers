[Documentation](https://sebllns.github.io/kmhelpers/@VERSION@/) | [Changelog](https://sebllns.github.io/kmhelpers/@VERSION@/changelog/)

## Install

From bioconda (includes `kmindex` and `ntcard`):

```bash
conda create -n kmhelpers -c conda-forge -c bioconda kmhelpers=@VERSION@
conda activate kmhelpers
```

From PyPI, then download the `kmtricks`, `kmindex` and `ntcard` binaries:

```bash
pip install kmhelpers==@VERSION@
kmhelpers install-deps
```

From source:

```bash
git clone --branch v@VERSION@ https://github.com/sebllns/kmhelpers
cd kmhelpers
conda env create -f conda/environment.yml -p ./.env
conda activate ./.env
```

## Update

Bioconda:

```bash
conda install -n kmhelpers -c conda-forge -c bioconda kmhelpers=@VERSION@
```

PyPI:

```bash
pip install --upgrade kmhelpers==@VERSION@
kmhelpers install-deps
```

Source (from the repository root):

```bash
git fetch --tags
git checkout v@VERSION@
conda env update -f conda/environment.yml -p ./.env --prune
```

Check the installed version with `kmhelpers --version`.

