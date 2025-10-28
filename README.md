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
- 🗜️ **ZSTD-based compression** with configurable block sizes
- 🔄 **Intelligent row reordering** using VP-tree nearest neighbor clustering
- 📊 **Resource monitoring** (CPU, memory, execution time)
- 🔍 **Query system** with FASTA/FASTQ support
- 📈 **Compression metrics** with histograms and performance tracking

## Project Structure

```
kmhelpers/
├── kmhelpers/
│   ├── core/              # Core utilities and index management
│   │   ├── utils.py       # Binary management, toolbox, kmindex operations
│   │   └── index.py       # Index and IndexRegistry classes
│   ├── operations/        # Compression and manipulation operations
│   │   └── compressor.py  # Compressor class and parameters
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

You need the following external binaries in a `bin/` directory:
- `kmindex`: Core indexing tool
- `block_compressor`: Matrix compression tool
- `block_decompressor`: Decompression tool
- `bitmatrix_shuffle`: Row reordering algorithm

### Install from source

```bash
# Clone the repository
git clone <repository-url>
cd kmhelpers

# Install in development mode
pip install -e .
```

### Install dependencies

```bash
pip install psutil
```

## Quick Start

### 1. Initialize the environment

```python
from kmhelpers import Main

# Initialize and check binaries
Main.init()
```

### 2. Working with indices

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
from kmhelpers import Compressor, CompressionParams

# Create compression parameters
params = CompressionParams(
    block_size=8388608,      # 8MB blocks
    group_size=0,            # Auto-calculate
    subsample_size=20000,    # Rows to sample for clustering
    threshold=0.0,
    enable_overwrite=False
)

# Initialize compressor
compressor = Compressor(enable_metrics=True)

# Compress an index
compressor.compress_index(params, index)
```

### 4. Query an index

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
- **Matrices**: Bit matrices where rows = k-mers, columns = samples
- **Metadata**: Stored in `index.json` with sample counts, parameters, etc.

Each matrix file has:
- **Header**: 49 bytes of metadata
- **Rows**: Each row is a bit vector indicating k-mer presence across samples
- **Bytes per row**: `(nb_samples + 7) // 8`

### Compression Pipeline

1. **Reordering**: Group similar rows together using VP-tree clustering
2. **Blocking**: Split matrix into fixed-size blocks
3. **Compression**: Apply ZSTD compression to each block
4. **Metrics**: Track histogram changes and compression ratios

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

#### `Index`
Properties:
- `index.nb_samples`, `index.nb_partitions`
- `index.smer_size`, `index.minim_size`
- `index.samples`: List of sample IDs

Methods:
- `index.get_matrix_path(partition, is_compressed)`
- `index.get_matrix_byte_size(partition)`
- `index.get_matrix_row_count(partition)`
- `index.check_structure()`

#### `IndexRegistry`
- `registry.list_indices()`: Get all index IDs
- `registry.get_index(index_id)`: Load specific index
- `registry.has_index(index_id)`: Check if index exists
- `registry.add_index(index)`: Register new index

### Operations

#### `Compressor`
- `compressor.compute_permutation(...)`: Calculate row reordering
- `compressor.compress_index(params, index)`: Compress entire index

#### `CompressionParams`
Configuration dataclass with fields:
- `block_size`: Bytes per compression block (default: 8388608)
- `group_size`: Grouping parameter (default: 0 = auto)
- `subsample_size`: Rows to sample for clustering (default: 20000)
- `threshold`: Compression threshold (default: 0.0)
- `enable_check`: Validate before compression
- `enable_overwrite`: Overwrite existing files

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

### Example 3: Compression with Metrics

```python
from kmhelpers import Main, IndexRegistry, Compressor, CompressionParams

Main.init()

registry = IndexRegistry("/data/indices")
index = registry.get_index("my_index")

params = CompressionParams(
    block_size=8388608,
    subsample_size=50000,
    enable_overwrite=False
)

compressor = Compressor(enable_metrics=True)

# Compute permutation for first partition
compressor.compute_permutation(
    params,
    input_matrix_path=index.get_matrix_path(0),
    matrix_columns_count=index.nb_samples,
    output_permutation_path="/data/perms/perm_0.txt",
    output_compressed_path="/data/compressed/matrix_0.zst",
    output_metric_path="/data/metrics/metrics_0.json"
)
```

## Performance Tips

1. **Subsampling**: Use larger `subsample_size` for better reordering (slower but better compression)
2. **Block size**: Larger blocks = better compression, more memory usage
3. **Partitions**: Process partitions in parallel for faster compression
4. **Monitoring**: Disable monitoring for production to reduce overhead

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

## Contributing

Contributions are welcome! Please:
1. Follow the existing code structure
2. Add unit tests for new features
3. Update documentation
4. Use type hints

## License

[Add license information]

## Citation

[Add citation information if applicable]

## Contact

[Add contact information]

---

**Version**: 0.0.1
**Status**: Development
