#!/usr/bin/env python3
"""
Script to generate fake FASTA samples with random contigs.
"""
import gzip
import random
import os

# Set seed for reproducibility
random.seed(42)

base_dir = os.path.dirname(os.path.abspath(__file__))
nucleotides = ['A', 'C', 'G', 'T']

sample_names = [
    "sample_001",
    "sample_002",
    "sample_003",
    "sample_004",
    "sample_005"
]

def generate_random_sequence(length):
    """Generate a random DNA sequence of specified length."""
    return ''.join(random.choices(nucleotides, k=length))

def create_fasta_file(filename, num_contigs=10, min_length=500, max_length=5000):
    """Create a compressed FASTA file with random contigs."""
    with gzip.open(filename, 'wt') as f:
        for i in range(num_contigs):
            contig_length = random.randint(min_length, max_length)
            sequence = generate_random_sequence(contig_length)

            # Write header
            f.write(f">contig_{i+1} length={contig_length}\n")

            # Write sequence in 80-character lines
            for j in range(0, len(sequence), 80):
                f.write(sequence[j:j+80] + "\n")

if __name__ == "__main__":
    # Generate 5 FASTA.gz files
    for sample in sample_names:
        filepath = os.path.join(base_dir, f"{sample}.fasta.gz")
        num_contigs = random.randint(8, 15)
        create_fasta_file(filepath, num_contigs=num_contigs)
        print(f"Created {sample}.fasta.gz with {num_contigs} contigs")

    print("All FASTA files created successfully!")