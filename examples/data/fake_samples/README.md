# Fake Samples Dataset

This directory contains synthetic FASTA files generated for testing and demonstration purposes.

## Data Content

The dataset consists of 5 compressed FASTA files:
- `s1/sample_001.fasta.gz` (9 contigs)
- `s1/sample_002.fasta.gz` (13 contigs)
- `s1/sample_003.fasta.gz` (13 contigs)
- `s2/sample_004.fasta.gz` (9 contigs)
- `s2/sample_005.fasta.gz` (8 contigs)

Each file contains randomly generated DNA sequences (contigs) with the following characteristics:
- Random nucleotide sequences (A, C, G, T)
- Contig lengths ranging from 500 to 5000 base pairs
- Standard FASTA format with 80 characters per line
- Gzip compression for efficient storage

## Regenerating the Data

To regenerate the sample files, run:

```bash
python3 generate_samples.py
```

The script uses a fixed random seed (42) for reproducibility.

## Creating a kmindex Index

### Prerequisites

kmindex requires a file-of-filenames (fof) as input. Create one first:

```bash
ls -1 $PWD/sample_*.fasta.gz > samples.fof
```

### Basic Index Creation

To create a basic presence/absence index:

```bash
kmindex build \
  -i my_index \
  -f samples.fof \
  -k 31 \
  --bloom-size 10000000
```

Key parameters:
- `-i/--index`: Output index path
- `-f/--fof`: Input file-of-filenames (required)
- `-k/--kmer-size`: K-mer size (default: 31, range: 8-255)
- `--bloom-size`: Bloom filter size for presence/absence indexing

### Abundance Indexing

To create an index with k-mer abundance information:

```bash
kmindex build \
  -i my_index \
  -f samples.fof \
  -k 31 \
  --nb-cell 10000000 \
  --bitw 2
```

Abundance parameters:
- `--nb-cell`: Number of cells in counting Bloom filter
- `--bitw`: Bits per cell (default: 2, creates 2^bitw abundance classes)
  - With `--bitw 3`, abundances are binned into 8 classes:
    - 0 → 0, 1 → [1,2), 2 → [2,4), 3 → [4,8), 4 → [8,16), 5 → [16,32), 6 → [32,64), 7 → [64,∞)

### Advanced Options

```bash
kmindex build \
  -i my_index \
  -f samples.fof \
  -k 31 \
  -m 10 \
  --bloom-size 10000000 \
  --hard-min 2 \
  --nb-partitions 0 \
  -t 4 \
  --cpr
```

Additional parameters:
- `-m/--minim-size`: Minimizer size (default: 10, range: 4-15)
- `--hard-min`: Minimum k-mer abundance threshold (default: 2)
- `--nb-partitions`: Number of partitions (0=auto, default: 0)
- `-t/--threads`: Number of threads (default: 14)
- `--cpr`: Compress intermediate files
- `-d/--run-dir`: kmtricks runtime directory
- `--km-path`: Path to kmtricks binary (if not in $PATH)

### Registering an Index

To register an index with a name for easier reuse:

```bash
kmindex build \
  -i my_index \
  -f samples.fof \
  -r my_samples \
  -k 31 \
  --bloom-size 10000000
```

Parameters:
- `-r/--register-as`: Index name for registration

### Reusing Parameters from a Registered Index

```bash
kmindex build \
  -i new_index \
  -f new_samples.fof \
  --from my_samples
```

This will use the same k-mer size, minimizer size, and other parameters from the registered index.

### Querying the Index

Once the index is created, you can query it:

```bash
kmindex query -i my_index -q query_sequences.fasta -o results.txt
```

### Using with kmhelpers

This package provides Python helpers for working with kmindex:

```python
from kmhelpers import Main, KmindexWrapper

# Initialize the environment
Main.init()

# Create wrapper
wrapper = KmindexWrapper()

# Build a presence/absence index
index = wrapper.build(
    index_path="my_index",
    input_files=["sample_001.fasta.gz", "sample_002.fasta.gz"],
    kmer_size=31,
    bloom_size=10000000
)

# Or build an abundance index
index = wrapper.build(
    index_path="my_abundance_index",
    input_files=["sample_001.fasta.gz", "sample_002.fasta.gz"],
    kmer_size=31,
    nb_cell=10000000,
    bitw=2
)

# Query the index
results_dir = wrapper.query(
    index="my_index",
    query_file="query.fasta",
    output_dir="query_results"
)

# Or use the index object directly
results_dir = wrapper.query(
    index=index,
    query_file="query.fasta",
    output_dir="query_results2"
)

# Access index properties
print(f"K-mer size: {index.kmer_size}")
print(f"Number of samples: {index.nb_samples}")
print(f"Sample names: {index.samples}")
```

## References

- kmindex documentation: https://github.com/tlemane/kmindex
- kmhelpers documentation: Check the main repository README
