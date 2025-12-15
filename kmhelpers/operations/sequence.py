from typing import Self
import gzip
from io import TextIOWrapper
from pathlib import Path


class Sequence:
    def __init__(self, content: str = "") -> None:
        self._content = content

    @property
    def length(self) -> int:
        return len(self._content)

    @property
    def content(self) -> str:
        return self._content
    
    def __str__(self) -> str:
        return self.content
    
    def __repr__(self) -> str:
        return f"Sequence(len='{self.length}')"


class FASTAReader:
    def __init__(self, filepath):
        self.filepath = Path(filepath)
        self._validate_format()
    
    def _validate_format(self):
        """Check file extension and compression type."""
        valid_exts = {'.fa', '.fasta', '.fna'}
        valid_compress = {'.gz', '.zst'}
        
        parts = self.filepath.suffixes
        if parts[-1] not in valid_compress:
            raise ValueError(f"Unsupported compression: {parts[-1]}")
        if len(parts) < 2 or parts[-2] not in valid_exts:
            raise ValueError(f"Unsupported sequence format: {parts[-2]}")
    
    def _open_file(self):
        """Open file with appropriate decompression."""
        if self.filepath.suffix == '.gz':
            return gzip.open(self.filepath, 'rt')
        elif self.filepath.suffix == '.zst':
            import zstandard
            fh = open(self.filepath, 'rb')
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
                line = line.rstrip('\n')
                if line.startswith('>'):
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
    
    def fetch_first_n(self, length):
        """Extract first N bases from contig."""
        with self._open_file() as fh:
            seq = ""
            for line in fh:
                line = line.rstrip('\n')
                if not line.startswith('>'):
                    seq += line
                    if len(seq) >= length:
                        break
            return Sequence(seq[:length])
    
    def iter_sequences(self):
        """Iterate all sequences. Yields (contig_name, sequence)."""
        with self._open_file() as fh:
            contig_name = None
            seq = ""
            
            for line in fh:
                line = line.rstrip('\n')
                if line.startswith('>'):
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
                line = line.rstrip('\n')
                if line.startswith('>'):
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
    seq = reader.fetch_first_n("contig_1", 50)
    print(f"First 50bp: {seq}")
    
    # Extract with range
    seq = reader.fetch_sequence("contig_1", start=10, end=60)
    print(f"10-60bp: {seq}")
    
    # Iterate all
    for name, seq in reader.iter_sequences():
        print(f"{name}: {len(seq)} bp")

