import gzip
import random
from io import TextIOWrapper
import os
from pathlib import Path
from typing import Optional
from .sequence import Sequence


class Fasta:
    """
    Contains a list a Sequences
    TODO: read a fasta from file
    """

    def __init__(self, sequences: Optional[list[Sequence]] = None) -> None:
        self._sequences = sequences if sequences is not None else []

    @property
    def sequences(self):
        return self._sequences

    @property
    def n_sequences(self):
        return len(self._sequences)

    def fill_random(self, num_sequences, average_size, min_size, header="sequence"):
        sequences = []
        # Calculate padding width based on number of sequences
        padding_width = len(str(num_sequences - 1))
        for i in range(num_sequences):
            seq_size = random.randint(min_size, average_size)
            # Zero-pad the index to maintain consistent naming
            padded_index = str(i).zfill(padding_width)
            sequence = Sequence(header=f"{header}{padded_index}")
            sequence.fill_random(seq_size)
            sequences.append(sequence)
        self._sequences = sequences

    def total_nucleotides(self):
        n = 0
        for _s in self._sequences:
            n += len(_s)
        return n

    def __str__(self) -> str:
        return self.to_fasta()

    def to_fasta(self) -> str:
        """Return FASTA formatted string with headers and sequences."""
        lines = []
        for _s in self._sequences:
            lines.append(_s.to_fasta())
        return "\n".join(lines)

    def __iter__(self):
        """Iterate over all sequences objects."""
        for _s in self._sequences:
            yield _s

    def __len__(self) -> int:
        return self.total_nucleotides()

    @staticmethod
    def create_random_test_dataset(
        output_dir: str, n_samples: int = 5, average_size=1000, min_size=100
    ):
        """
        Create random sequences FASTA files for testing.

        :param output_dir: Output directory for test FASTA files
        :type output_dir: str
        :param n_samples: Number of random sequences to generate
        :type n_samples: int
        """
        os.makedirs(output_dir, exist_ok=True)
        fasta = Fasta()
        fasta.fill_random(
            num_sequences=n_samples,
            average_size=average_size,
            min_size=min_size,
            header=os.path.basename(output_dir) + "_",
        )
        for _i, sequence in enumerate(fasta):
            output_file = os.path.join(output_dir, f"{sequence.header}.fasta")
            with open(output_file, "w") as f:
                f.write(sequence.to_fasta())


class FASTAReader:
    def __init__(self, filepath):
        self.filepath = Path(filepath)
        self._validate_format()

    def _validate_format(self):
        """Check file extension and compression type."""
        valid_exts = {".fa", ".fasta", ".fna"}
        valid_compress = {".gz", ".zst"}

        parts = self.filepath.suffixes
        if parts[-1] not in valid_compress:
            raise ValueError(f"Unsupported compression: {parts[-1]}")
        if len(parts) < 2 or parts[-2] not in valid_exts:
            raise ValueError(f"Unsupported sequence format: {parts[-2]}")

    def _open_file(self):
        """Open file with appropriate decompression."""
        if self.filepath.suffix == ".gz":
            return gzip.open(self.filepath, "rt")
        elif self.filepath.suffix == ".zst":
            import zstandard

            fh = open(self.filepath, "rb")
            dctx = zstandard.ZstdDecompressor()
            return TextIOWrapper(dctx.stream_reader(fh))
        else:
            raise ValueError(f"Unknown compression: {self.filepath.suffix}")

    def fetch_sequence(self, contig_name, start=None, end=None):
        """
        Extract sequence for a contig, optionally with range.
        Returns sequence string without header.
        """
        with self._open_file() as fh:
            seq = None
            for line in fh:
                line = line.rstrip("\n")
                if line.startswith(">"):
                    if seq is not None:
                        break
                    if line[1:].split()[0] == contig_name:
                        seq = ""
                elif seq is not None:
                    seq += line

            if seq is None:
                raise ValueError(f"Contig '{contig_name}' not found")

            if start is not None or end is not None:
                return seq[start:end]
            return seq

    def fetch_first_n(self, length, offset=0):
        """Extract first N bases from contig."""
        with self._open_file() as fh:
            seq = ""
            for line in fh:
                line = line.rstrip("\n")
                if not line.startswith(">"):
                    seq += line
                    if len(seq) >= offset + length:
                        break
            return Sequence(
                content=seq[offset : offset + length],
                header=f"{self.filepath.name}.S{offset}.L{length}",
            )

    def iter_sequences(self):
        """Iterate all sequences. Yields (contig_name, sequence)."""
        with self._open_file() as fh:
            contig_name = None
            seq = ""

            for line in fh:
                line = line.rstrip("\n")
                if line.startswith(">"):
                    if contig_name is not None:
                        yield contig_name, seq
                    contig_name = line[1:].split()[0]
                    seq = ""
                else:
                    seq += line

            if contig_name is not None:
                yield contig_name, seq

    def iter_with_header(self):
        """Iterate all sequences with full header. Yields (header, sequence)."""
        with self._open_file() as fh:
            header = None
            seq = ""

            for line in fh:
                line = line.rstrip("\n")
                if line.startswith(">"):
                    if header is not None:
                        yield header, seq
                    header = line[1:]
                    seq = ""
                else:
                    seq += line

            if header is not None:
                yield header, seq


# Example usage
if __name__ == "__main__":
    reader = FASTAReader("sequences.fa.gz")

    # Extract first 50 bases
    seq = reader.fetch_first_n(50)
    print(f"First 50bp: {seq}")

    # Extract with range
    seq = reader.fetch_sequence("contig_1", start=10, end=60)
    print(f"10-60bp: {seq}")

    # Iterate all
    for name, seq in reader.iter_sequences():
        print(f"{name}: {len(seq)} bp")
