# kmhelpers

[![License](https://img.shields.io/badge/license-GPL--3.0--only-blue)](https://github.com/sebllns/kmhelpers/blob/main/LICENSE)
[![PyPI](https://img.shields.io/pypi/v/kmhelpers)](https://pypi.org/project/kmhelpers/)
[![Bioconda](https://img.shields.io/conda/vn/bioconda/kmhelpers)](https://anaconda.org/bioconda/kmhelpers)
[![Anaconda](https://img.shields.io/conda/p/bioconda/kmindex?logo=anaconda&label=bioconda%7Cplatform&color=green)](https://anaconda.org/bioconda/kmhelpers)
[![Tests](https://github.com/sebllns/kmhelpers/actions/workflows/tests.yml/badge.svg)](https://github.com/sebllns/kmhelpers/actions/workflows/tests.yml)
[![DOI](https://zenodo.org/badge/1219077365.svg)](https://doi.org/10.5281/zenodo.23730969)

<img src="https://raw.githubusercontent.com/sebllns/kmhelpers/main/assets/kmhelpers-logo-v1.png" alt="kmhelpers logo" width="64" height="64">

A Python toolkit that automates the lifecycle of [kmindex](https://github.com/tlemane/kmindex) k-mer indexes, from raw sequencing samples to queries. It provides a command-line interface and a matching Python API.

- **Design**: discovers samples, counts their k-mers with [ntCard](https://github.com/BirolLab/ntCard), and groups them into sub-indexes with Bloom filters sized to each group.
- **Build**: checks files, disk space and memory before building, then builds and merges the sub-indexes with kmindex.
- **Update**: adds new samples to an existing index without recounting the samples already indexed.
- **Query**: searches FASTA/FASTQ sequences (plain or compressed) and writes TSV, JSON or YAML results with per-sequence and per-sample statistics.
- **Manage**: compresses indexes, registers several indexes as one (in development), and runs multi-step workflows from YAML pipeline files.

**Documentation:** <https://sebllns.github.io/kmhelpers/>

## Installation

Requires Python 3.10 or later on Linux or macOS.

### With pip

```bash
pip install kmhelpers
kmhelpers install-deps
```

`install-deps` downloads the `kmtricks`, `kmindex` and `ntcard` binaries next to the `kmhelpers` executable, so a virtual environment (`python -m venv`) is recommended.

### With Conda (Bioconda)

```bash
conda install -c conda-forge -c bioconda kmhelpers
```

`kmindex` and `ntcard` are installed as dependencies.

### Check the installation

```bash
kmhelpers --version
kmhelpers check-deps
```

`kh` is a short alias for `kmhelpers`. To install from source, see the [installation guide](https://sebllns.github.io/kmhelpers/latest/getting-started/installation/).

## Quick start

```bash
# 1. Design: list the samples of a directory and compose the index definitions
kmhelpers design /data/sequences -o coli_db/ -n coli

# 2. Build the index from these definitions
kmhelpers build coli_db/compose/coli/*/coli.yaml -o coli_build/

# 3. Query it with FASTA/FASTQ sequences
kmhelpers query -r coli_build/ -o results/ query.fa
```

The [E. coli tutorial](https://sebllns.github.io/kmhelpers/latest/tutorials/ecoli/) walks through these steps on real data, and the [command reference](https://sebllns.github.io/kmhelpers/latest/commands/) lists every option.

## Citation

If you use kmhelpers, please cite the archived software:

> Bellenous S., Jaron K. S., Peterlongo P. *kmhelpers: A Python toolkit for automated management of genomic indexes*. Zenodo. <https://doi.org/10.5281/zenodo.23730969>

A paper is under review at the [Journal of Open Source Software](https://joss.theoj.org/).

## Disclaimer

`kmhelpers` is provided "as is", without warranty. Building, updating or compressing an index modifies data in place, so back up important data first, and if you are unsure about an operation, [ask here](https://github.com/sebllns/kmhelpers/discussions) before running it.

## License

GNU General Public License v3.0 only, see [LICENSE](https://github.com/sebllns/kmhelpers/blob/main/LICENSE).

Copyright (c) 2026 Sébastien Bellenous, Genscale, INRIA

## Contact

- **Author**: [Sébastien Bellenous](https://github.com/sebllns)
- **Supervisor**: [Pierre Peterlongo](https://github.com/pierrepeterlongo)
- **Email**: kmhelpers@groupes.renater.fr
- **Issues and discussions**: <https://github.com/sebllns/kmhelpers>
- **Changelog**: [CHANGELOG.md](https://github.com/sebllns/kmhelpers/blob/main/CHANGELOG.md)

## Acknowledgements

The authors thank Téo Lemane for developing `kmindex` and for his responsiveness in addressing feature requests and issues raised during the development of `kmhelpers`. We acknowledge the GenOuest core facility (<https://www.genouest.org>) for providing the computing infrastructure. The work was funded by the Inria Challenge "OmicFinder" (<https://project.inria.fr/omicfinder/>), and by the state funding managed by the French National Research Agency under the France 2030 program [ANR-22-PEAE-0005].
