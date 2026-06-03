# count-kmers

Count the number of distinct k-mers in a sequence file using ntcard.

## Usage

```
kmhelpers count-kmers [OPTIONS]
```

## Description

Wraps [ntCard](https://github.com/BirolLab/ntCard) to count distinct k-mers in a single sequence file. Supports FASTA, FASTQ, SAM, and BAM formats.

## Examples

```bash
# Count k-mers with default settings (k=31, 8 threads)
kmhelpers count-kmers -i reads.fa

# Custom k-mer size
kmhelpers count-kmers -i reads.fa -k 25

# With threading
kmhelpers count-kmers -i reads.fa -k 31 -t 16
```

## Options

| Option | Description |
|--------|-------------|
| `-i, --input-file FILE` | Input sequence file (FASTA, FASTQ, SAM, BAM) (required) |
| `-k, --kmer-size INT` | K-mer size (default: 31) |
| `-t, --threads INT` | Number of threads (default: 8) |
| `-v, --verbose` | Verbose output |