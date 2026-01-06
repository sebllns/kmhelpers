# kmhelpers

A Python toolkit for managing, compressing, and querying k-mer indices efficiently.

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

## Project Structure

```
kmhelpers/
├── kmhelpers/
│   ├── core/              # Core utilities and index management
│   │   ├── utils.py       # Binary management, toolbox, kmindex operations
│   │   ├── index.py       # Index and IndexRegistry classes
│   │   └── wrapper.py     # KmindexWrapper high-level interface
│   ├── operations/        # Compression and manipulation operations
│   │   ├── compressor.py  # Compressor class and parameters
│   │   └── fof.py         # FofManager for file-of-files operations
│   ├── metrics/           # Performance tracking
│   │   └── compression_metrics.py
│   └── cli/               # Command-line scripts
│       ├── compress_index.py
│       └── query_index.py
├── tests/                 # Unit tests (to be added)
├── examples/              # Usage examples
├── docs/                  # Additional documentation
└── bin/                   # External binaries (not in repo)
    ├── kmindex
    ├── block_compressor
    ├── block_decompressor
    └── bitmatrix_shuffle
```

## Installation

### Prerequisites

You need the following external binaries:
- `kmindex >= 0.5.3`: Core indexing tool
- `block_compressor`: Matrix compression tool
- `block_decompressor`: Decompression tool
- `bitmatrix_shuffle`: Column reordering algorithm

### Quick Install with Conda (Recommended)

```bash
# Clone the repository
git clone <repository-url>
cd kmhelpers

# Create environment with kmindex pre-installed
conda env create -f conda/environment.yml

# Activate the environment
conda activate kmhelpers
```

This automatically installs kmindex >= 0.5.3 from bioconda along with all Python dependencies.

### Install with Pip

```bash
# Clone the repository
git clone <repository-url>
cd kmhelpers

# Install kmhelpers in development mode
pip install -e .
```

Then install kmindex separately:

```bash
# Via bioconda (requires conda/mamba)
conda install -c bioconda kmindex>=0.5.3

# Or compile from source and add to PATH
git clone <kmindex-repo>
cd kmindex && mkdir build && cd build
cmake .. && make
export PATH=$(pwd):$PATH  # Add to your shell profile for persistence
```

### Override kmindex Installation

If you prefer to use a custom-compiled kmindex or a different version:

1. **Install kmindex from source:**
   ```bash
   # Build kmindex from your source
   git clone <kmindex-repo>
   cd kmindex && mkdir build && cd build
   cmake .. && make
   ```

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

The runtime check will automatically find kmindex in your PATH, whether installed via conda or compiled from source.

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

### 2. Building an index (NEW in v0.3.0)

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

### 4. Managing file-of-files (FOF) (NEW in v0.3.0)

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

### Query Index

```bash
python -m kmhelpers.cli.query_index \
    --input /path/to/index \
    --output /path/to/results \
    --index GENOMIC_HUMAN_19 \
    --query query.fasta \
    --zvalue 0 \
    --threshold 0.0
```

### Compress Index (deprecated, use Python API)

```bash
python -m kmhelpers.cli.compress_index \
    --input /path/to/source \
    --output /path/to/compressed \
    --index GENOMIC_HUMAN_19
```

## API Reference

### Core Classes

#### `Main`
- `Main.init()`: Initialize environment and check binaries

#### `Bin`
- `Bin.get_bin_dir()`: Get binary directory path
- `Bin.get_kmindex_path()`: Get kmindex binary path
- `Bin.check_all()`: Validate all required binaries

#### `Toolbox`
- `Toolbox.get_canonical_path(path)`: Resolve absolute path
- `Toolbox.run_cmd(cmd)`: Execute command and capture output
- `Toolbox.monitor_cmd(cmd)`: Execute with resource monitoring
- `Toolbox.save_to_json_file(data, filename)`: Save JSON data

#### `Kmindex`
- `Kmindex.get_partition_count(dir, index_id)`: Get number of partitions
- `Kmindex.get_sample_count(dir, index_id)`: Get number of samples
- `Kmindex.get_matrix_path(index_path, partition, is_compressed)`: Get matrix file path
- `Kmindex.query_index(...)`: Execute k-mer query
- `Kmindex.register_index_in_json(...)`: Register index in manifest

#### `KmindexWrapper` (NEW in v0.3.0)
High-level interface for building and querying indices:
- `wrapper.build(index_path, fof_file, kmer_size, bloom_size, ...)`: Build an index
- `wrapper.query(index, query_file, output_dir, ...)`: Query an index
- `wrapper.create_fof_file(input_files, fof_path)`: Create FOF from file list
- `wrapper.fof_manager`: Access to FofManager instance

#### `FofManager` (NEW in v0.3.0)
Comprehensive file-of-files management:
- `manager.create_fof_file(input_files, fof_path, ...)`: Create FOF from list
- `manager.create_fof_from_directory(directory, fof_path, ...)`: Create FOF from directory
- `manager.list_files_in_directory(directory, recursive, extensions)`: List matching files
- `manager.load_fof_file(fof_path)`: Load sample IDs
- `manager.load_with_paths(fof_path)`: Load samples with paths as dict
- `manager.get_sample_ids(fof_path)`: Get sample IDs
- `manager.validate_fof_file(fof_path)`: Validate FOF format
- `manager.validate_input_files(file_list)`: Check files exist
- `manager.extract_sample_name(file_path)`: Extract name from path
- `manager.append_to_fof(fof_path, new_files)`: Append files to FOF
- `manager.copy_fof(source, dest)`: Copy FOF file

#### `KmtricksIndex`
Properties:
- `index.nb_samples`, `index.nb_partitions`
- `index.kmer_size`, `index.minim_size`
- `index.samples`: List of sample IDs

Methods:
- `index.get_matrix_path(partition, is_compressed)`
- `index.get_matrix_byte_size(partition)`
- `index.get_matrix_row_count(partition)`
- `index.check_structure()`

#### `KmindexRegistry`
- `registry.list_indices()`: Get all index IDs
- `registry.get_index(index_id)`: Load specific index
- `registry.has_index(index_id)`: Check if index exists
- `registry.add_index(index)`: Register new index

### Operations

#### `Compressor`

The `Compressor` class provides methods for compressing k-mer indices with optional permutation-based reordering:

**Methods:**
- `compress_file(params, input_matrix_path, matrix_columns_count, ...)`: Compress a single matrix file
- `compress_partition(params, idx, partition, ...)`: Compress a single partition with size comparison
- `compress_index_selection(params, idx, ref_matrix, matrix_list, ...)`: Compress selected partitions
- `compress_full_index(params, idx, output_dir)`: Compress all partitions of an index

**Features:**
- Permutation-based column reordering for improved compression ratios
- Optional size comparison between ordered and unordered compression
- Metrics collection in JSON format
- CSV reports for compression statistics
- Configurable reference partition for permutation computation

#### `CompressionParams`
Configuration dataclass with fields:
- `block_size`: Bytes per compression block (default: 8388608)
- `group_size`: Grouping parameter (default: 0 = auto)
- `subsample_size`: Rows to sample for distance calcultation (default: 20000)
- `threshold`: Compression threshold (default: 0.0)
- `enable_check`: Validate before compression
- `enable_overwrite`: Overwrite existing files
- `with_size_comparison`: Enable size comparison reporting (default: True)
- `force_permutation`: Force permutation computation (default: False)

### Metrics

#### `PermutationData`
Tracks reordering metrics:
- Distance statistics (avg, stdev) before/after
- Compressibility factor
- Timing data

#### `CompressionData`
Tracks compression metrics:
- Block configuration
- Compression ratios
- Histograms (original vs reordered)
- Timing data

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

### Example 2: Batch Query

```python
from kmhelpers import Main, Kmindex
import os

Main.init()

queries = ["query1.fasta", "query2.fasta", "query3.fasta"]
index_path = "/data/indices"
output_base = "/data/results"

for query_file in queries:
    query_name = os.path.splitext(os.path.basename(query_file))[0]
    output_dir = os.path.join(output_base, query_name)

    result = Kmindex.query_index(
        names=["index1", "index2"],
        index_path=index_path,
        output_dir=output_dir,
        format="json",
        fastx=query_file,
        monitor=True
    )

    if result:
        stdout, stats = result
        print(f"{query_name}: {stats['execution_time_ms']}ms")
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

## Performance Tips

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

[Add license information]

## Citation

[Add citation information if applicable]

## Contact

[Add contact information]

---

**Version**: 0.5.5
**Status**: Development

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for detailed version history.
