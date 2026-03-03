# kmhelpers

<div style="text-align: center;">

![logo](kmhelpers-logo-v1.png "Kmhelpers Logo")



</div>

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Getting Started](#getting-started)
- [Installation with kmhelpersctl](#installation-with-kmhelpersctl-recommended)
  - [Quick Installation](#21-quick-installation-recommended)
  - [Verify Installation](#22-verify-installation)
  - [Custom Installation Path](#23-custom-installation-path)
  - [Install Components Separately](#24-install-components-separately)
  - [Getting Help](#25-getting-help)
- [Manual Installation](#manual-installation)
- [Quick Start](#quick-start)
- [Core Concepts](#core-concepts)
- [Command-Line Interface](#command-line-interface)
- [API Reference](#api-reference)
- [Examples](#examples)
- [Performance Tips for Compression](#performance-tips-for-compression)
- [Troubleshooting](#troubleshooting)
- [License](#license)
- [Contact](#contact)
- [Changelog](#changelog)

## Overview

**kmhelpers** provides a comprehensive interface for working with k-mer indices, specifically designed for handling large-scale genomic data. It offers tools for:

- **Index Management**: Register, validate, and query k-mer indices
- **Compression**: Optimize index storage through intelligent reordering and block compression
- **Querying**: Fast k-mer lookup with resource monitoring
- **Metrics**: Track compression performance and efficiency

## Features

- 🗂️ **Object-oriented index management** with properties and metadata
- 🏗️ **High-level index building** with KmindexWrapper for easy index creation
- 📁 **FOF (File-of-Files) management** for organizing input files
- 🗜️ **ZSTD-based compression** with configurable block sizes
- 🔄 **Intelligent column reordering** using VP-tree nearest neighbor clustering
- 📊 **Resource monitoring** (CPU, memory, execution time)
- 🔍 **Query system** with FASTA/FASTQ support
- 📈 **Compression metrics** with histograms and performance tracking

## Getting started

Clone the repository and navigate to it

```bash
git clone https://gitlab.inria.fr/omicfinder/kmhelpers
git checkout dev/v0.5.5
cd kmhelpers
```

Once the repository is cloned, you have two options for installation:
- [**Automated**](#installation-with-kmhelpersctl-recommended): Use the `kmhelpersctl` script for automated setup
- [**Manual**](#manual-installation): Follow step-by-step installation instructions

## Installation with kmhelpersctl (Recommended)

kmhelpersctl is a bash utility script that simplifies installation of kmhelpers and kmindex.

### 2.1 Quick Installation (Recommended)

If you have **Conda** installed, the easiest way to install kmhelpers and all dependencies in one go:

```bash
./kmhelpersctl.sh install all
```

This will automatically:
- Install kmindex from bioconda
- Install kmhelpers Python package
- Set up shell completions for both tools
- Create activation aliases for convenient use
- Add tools to your PATH

**Prerequisites:** Conda (Miniconda or Anaconda) must be installed. If you don't have it, see [Installation Instructions](https://docs.conda.io/projects/conda/en/latest/user-guide/install/index.html).

### 2.2 Verify Installation

After installation, you need to reload your shell for the changes to take effect:

```bash
# Reload your shell
source ~/.bashrc
# Or if using zsh
source ~/.zshrc
```

Once reloaded, verify the installation:

```bash
# Check the installed version
kmhelpersctl --version

# View available commands
kmhelpersctl --help
```

### 2.3 Custom Installation Path

By default, kmhelpers installs to `~/.kmhelpers`. To use a different path:

```bash
./kmhelpersctl.sh -w /custom/path install all
```

The installation path is stored in `KMHELPERS_PATH` environment variable, which is loaded automatically when you run `kmhelpersctl` after installation.

### Override Path Per Command

After installation, you can also manually point to another path with any command:
```bash
kmhelpersctl -w /custom/path <command>
```

### 2.4 Install Components Separately

If you prefer to install components individually:

```bash
# Install only kmindex from bioconda
./kmhelpersctl.sh install kmindex

# Install only the kmhelpers Python package
./kmhelpersctl.sh install python

# Install zsh completions
./kmhelpersctl.sh completion kmindex
./kmhelpersctl.sh completion kmhelpersctl
```

### 2.5 Getting Help

For detailed information on any command, use `help`, `-h`, or `--help`:

```bash
# Show all available commands
kmhelpersctl -h

# Show detailed help for a command
kmhelpersctl <command> help
# Equivalent to
kmhelpersctl <command> -h
# Or
kmhelpersctl <command> --help

# Examples
kmhelpersctl install -h
kmhelpersctl install kmindex -h
kmhelpersctl register -h
```

## Manual Installation

### Quick Install with Conda 

```bash
# Create environment with kmindex pre-installed
conda env create -f conda/environment.yml

# Activate the environment
conda activate kmhelpers
```

This automatically installs kmindex >= 0.5.3 from bioconda along with all Python dependencies.

### Install with Pip

```bash
# Install kmhelpers in development mode
pip install -e .
```

Then install kmindex separately:

```bash
# Via bioconda (requires conda/mamba)
conda install -c bioconda kmindex>=0.5.3
```

### Override kmindex Installation (advanced)

If you prefer to use a custom-compiled kmindex or a different version:

1. **Install kmindex from source:**
    Follow the guide:
    https://tlemane.github.io/kmindex/installation/#install-from-sources


2. **Add the binary to your PATH:**
   ```bash
   # Temporary (for current session)
   export PATH=/path/to/kmindex/build:$PATH

   # Permanent (add to ~/.bashrc or ~/.zshrc)
   echo 'export PATH=/path/to/kmindex/build:$PATH' >> ~/.bashrc
   ```

3. **Verify installation:**
   ```bash
   kmindex --version
   ```

## Quick Start

### 1. Initialize the environment

```python
from kmhelpers import Main, Bin

# Initialize and check binaries
Main.init()

# Optionally check specifically for kmindex with helpful error message
Bin.check_kmindex()
```

If kmindex is not found, you'll see a helpful error message with installation instructions for bioconda or source compilation.

### 2. Building an index

```python
from kmhelpers import Main, KmindexWrapper

# Initialize
Main.init()

# Create wrapper
wrapper = KmindexWrapper()

# Create index from directory of FASTA files
wrapper.fof_manager.create_fof_from_directory(
    directory="data/samples",
    fof_path="samples.fof"
)

# Build presence/absence index
index = wrapper.build(
    index_path="my_index",
    fof_file="samples.fof",
    kmer_size=31,
    bloom_size=10000000
)

# Access index properties
print(f"Built index with {index.nb_samples} samples")
print(f"K-mer size: {index.kmer_size}")
```

### 3. Working with indices

```python
from kmhelpers import IndexRegistry, Index

# Load an index registry
registry = IndexRegistry("/path/to/indices")

# List available indices
print(registry.list_indices())

# Get a specific index
index = registry.get_index("GENOMIC_HUMAN_19")

# Access index properties
print(f"Samples: {index.nb_samples}")
print(f"Partitions: {index.nb_partitions}")
print(f"K-mer size: {index.smer_size}")

# Iterate through all indices
for idx in registry:
    print(f"{idx.index_id}: {idx.nb_samples} samples")
```

### 3. Compression workflow

```python
from kmhelpers import Compressor, CompressionParams, PermutationFlag

# Create compression parameters
params = CompressionParams(
    block_size=8388608,           # 8MB blocks
    group_size=0,                 # All columns
    subsample_size=20000,         # Rows to sample for computing distances
    threshold=0.0,
    enable_overwrite=False,
    with_size_comparison=True     # Enable size comparison CSV
)

# Initialize compressor with metrics
compressor = Compressor(enable_metrics=True)

# Compress all partitions of an index
compressor.compress_full_index(params, index, output_dir="/path/to/output")

# Or compress selected partitions
compressor.compress_index_selection(
    params,
    index,
    ref_matrix=1,                          # Reference partition for permutation
    matrix_list=[2, 3, 4],                 # Other partitions to compress
    permutation_flag=PermutationFlag.PERMUTATION_ENABLED,
    compare_unordered=True                 # Compare with unordered compression
)
```

### 4. Managing file-of-files (FOF)

```python
from kmhelpers import FofManager

manager = FofManager()

# Create FOF from a directory
fof_path = manager.create_fof_from_directory(
    directory="/path/to/samples",
    fof_path="samples.fof",
    recursive=True  # Include subdirectories
)

# Load sample IDs from FOF
samples = manager.get_sample_ids("samples.fof")
print(f"Found {len(samples)} samples")

# Load with paths
sample_map = manager.load_with_paths("samples.fof")
for name, path in sample_map.items():
    print(f"{name}: {path}")

# Validate FOF file
manager.validate_fof_file("samples.fof")

# List files in directory matching extensions
files = manager.list_files_in_directory(
    directory="/path/to/samples",
    extensions=[".fasta.gz", ".fastq.gz"]
)
```

### 5. Query an index

```python
from kmhelpers import Kmindex

# Query with monitoring
result = Kmindex.query_index(
    names=["sample1", "sample2"],
    index_path="/path/to/index",
    output_dir="/path/to/results",
    format="json",
    fastx="/path/to/query.fasta",
    zvalue=0,
    threshold=0.0,
    monitor=True
)

stdout, resource_stats = result
print(f"Query time: {resource_stats['execution_time_ms']}ms")
print(f"Peak memory: {resource_stats['max_memory_mb']}MB")
```

## Core Concepts

### Index Structure

A k-mer index consists of:
- **Partitions**: 256 matrix files (default) splitting k-mer space
- **Matrices**: Bit matrices (Bloom Filters) where rows = k-mers, columns = samples  
Each row is a bit vector indicating k-mer presence across samples  
- **Metadata**: Stored in `index.json` with sample counts, parameters, etc.

### Compression Pipeline

The compression workflow consists of:

1. **Reference Selection**: Choose one partition as the reference matrix
2. **Permutation Computation**: Analyze the reference matrix to find optimal column (sample) ordering using VP-tree clustering
3. **Reference Compression**: Compress the reference matrix with the computed column permutation
4. **Permutation Application**: Apply the same column permutation to other partitions
5. **Block Compression**: Split matrices into fixed-size blocks and compress with ZSTD
6. **Metrics Collection**: Track compression ratios, histograms, and optional size comparisons

**Key Features:**
- Single column permutation computed from reference matrix, applied to all partitions
- Reorders columns (samples) to group similar patterns together for better compression
- Optional size comparison between ordered and unordered compression
- Detailed metrics in JSON format for each partition
- CSV summary with original, ordered, and optionally unordered sizes

### Index Registry

The `IndexRegistry` manages multiple indices through a single `index.json` file:

```json
{
  "index": {
    "index_id_1": {
      "nb_samples": 1000,
      "nb_partitions": 256,
      "bloom_size": 10000000,
      "smer_size": 31,
      ...
    }
  },
  "path": "/absolute/path/to/indices"
}
```

## Command-Line Interface

## API Reference

## Examples

### Example 1: Index Information

```python
from kmhelpers import Main, IndexRegistry

Main.init()

registry = IndexRegistry("/data/indices")
index = registry.get_index("my_index")

print(f"Index: {index.index_id}")
print(f"Samples: {index.nb_samples}")
print(f"Partitions: {index.nb_partitions}")
print(f"K-mer size: {index.smer_size}")
print(f"Total elements: {sum(index.get_matrix_element_count(p) for p in range(index.nb_partitions))}")
```

### Example 2: Query

```python

```

### Example 3: Compression with Metrics and Size Comparison

```python
from kmhelpers import Main, IndexRegistry, Compressor, CompressionParams, PermutationFlag

Main.init()

registry = IndexRegistry("/data/indices")
index = registry.get_index("my_index")

params = CompressionParams(
    block_size=8388608,
    subsample_size=50000,
    enable_overwrite=False,
    with_size_comparison=True  # Generate sizes.csv
)

compressor = Compressor(enable_metrics=True)

# Compress with size comparison
output_dir = "/data/compressed"
compressor.compress_index_selection(
    params,
    index,
    ref_matrix=1,
    matrix_list=list(range(2, 10)),  # Compress partitions 2-9
    output_dir=output_dir,
    permutation_flag=PermutationFlag.PERMUTATION_ENABLED,
    compare_unordered=True  # Also compress without ordering for comparison
)

# Results will be in:
# - /data/compressed/matrices/*.zst (compressed matrices)
# - /data/compressed/permutation.bin (permutation file)
# - /data/compressed/metrics/*.json (compression metrics)
# - /data/compressed/metrics/sizes.csv (size comparison data)
```

## Performance Tips for Compression

1. **Subsampling**: Use larger `subsample_size` for better reordering (slower but better compression)
2. **Block size**: Larger blocks = better compression, more memory usage
3. **Reference Matrix**: Choose a representative partition as reference for best permutation quality
4. **Partitions**: Process partitions in parallel for faster compression
5. **Monitoring**: Disable monitoring for production to reduce overhead
6. **Size Comparison**: Disable `with_size_comparison` and `compare_unordered` in production for faster compression

## Troubleshooting

### Binary not found
```python
# Check binary paths
from kmhelpers import Bin
print(Bin.get_bin_dir())
Bin.check_all()
```

### Import errors after restructure
```python
# Use absolute imports
from kmhelpers.core.utils import Kmindex
from kmhelpers.core.index import Index
```

### Index structure validation
```python
from kmhelpers import Kmindex

# Check if all files are present
Kmindex.check_index_structure("/path/to/index", partition_count=256)
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

Copyright (c) 2026 Sébastien BELLENOUS

## Contact

For questions, bug reports, or contributions, please contact:

- **Author**: Sébastien BELLENOUS
- **Email**: kmhelpers@groupes.renater.fr
- **Repository**: [GitLab](https://gitlab.inria.fr/omicfinder/kmhelpers)

---

**Version**: 0.6.0
**Status**: Development

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for detailed version history.
