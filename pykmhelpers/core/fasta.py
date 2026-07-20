import gzip
import random
from io import TextIOWrapper
import os
from pathlib import Path
from typing import Optional
from .sequence import Sequence


def open_sequence_file(filepath):
    """Open a plain, gzip (.gz) or zstandard (.zst) sequence file as text."""
    filepath = Path(filepath)
    suffix = filepath.suffix.lower()
    if suffix == ".gz":
        return gzip.open(filepath, "rt")
    if suffix == ".zst":
        import zstandard

        fh = open(filepath, "rb")
        dctx = zstandard.ZstdDecompressor()
        return TextIOWrapper(dctx.stream_reader(fh))
    return open(filepath, "rt")


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


class SequenceValidator:
    """
    Validate a FASTA/FASTQ file for structural correctness.

    The format is detected from the file extension and can be forced with
    `fmt`. Plain, gzip (.gz) and zstandard (.zst) files are supported.

    Checks performed:
      FASTA - first record starts with '>', headers are non-empty, every
              header has sequence data, sequence characters are IUPAC valid.
      FASTQ - records are complete 4-line blocks, header starts with '@',
              separator starts with '+', quality length matches sequence
              length, sequence and quality characters are valid.

    Errors are collected as (line_num, reason) tuples, mirroring FofValidator.

    Example:
        >>> v = SequenceValidator("reads.fastq.gz")
        >>> if not v.validate():
        ...     v.print_errors()
    """

    FASTA_EXT = {".fa", ".fasta", ".fna"}
    FASTQ_EXT = {".fq", ".fastq"}

    # DNA IUPAC codes (both cases) plus gap symbols. Matches seqkit's
    # --seq-type dna validation so both engines agree. Permissive on ambiguity
    # codes: the goal is to catch corruption, not enforce a pure ACGT alphabet.
    VALID_SEQ_CHARS = frozenset("ACGTRYSWKMBDHVNacgtryswkmbdhvn-.")

    # Printable ASCII range shared by all FASTQ quality encodings.
    MIN_QUAL, MAX_QUAL = 33, 126
    VALID_QUAL_CHARS = frozenset(chr(c) for c in range(MIN_QUAL, MAX_QUAL + 1))

    def __init__(
        self,
        filepath,
        fmt: Optional[str] = None,
        max_errors: int = 100,
        use_seqkit: bool = True,
        strict: bool = True,
    ):
        self.filepath = Path(filepath)
        if not self.filepath.exists():
            raise FileNotFoundError(f"Sequence file not found: {self.filepath}")
        self.max_errors = max_errors
        self.use_seqkit = use_seqkit
        # strict also runs the per-character alphabet check (the slow part);
        # when False only the cheaper structural checks are performed.
        self.strict = strict
        # Engine actually used by the last validate() call: "seqkit" or "builtin".
        self.engine: Optional[str] = None
        self.fmt = (fmt or self._detect_format()).lower()
        if self.fmt not in ("fasta", "fastq"):
            raise ValueError(f"Unsupported format: {self.fmt}")
        self.errors: list[tuple[int, str]] = []

    def _detect_format(self) -> str:
        """Detect fasta/fastq from the file extension, ignoring compression."""
        for suffix in reversed(self.filepath.suffixes):
            s = suffix.lower()
            if s in self.FASTA_EXT:
                return "fasta"
            if s in self.FASTQ_EXT:
                return "fastq"
        raise ValueError(
            f"Cannot detect FASTA/FASTQ format from: {self.filepath.name}"
        )

    def validate(self) -> bool:
        """
        Run validation and return True if no errors were found.

        Uses seqkit when available (and use_seqkit is set), otherwise falls
        back to the builtin Python checks. The engine used is recorded in
        `self.engine`.
        """
        self.errors = []
        if self.use_seqkit and self._validate_with_seqkit():
            return not self.errors
        return self._validate_builtin()

    def _validate_with_seqkit(self) -> bool:
        """Try validating via seqkit. Return False if seqkit is unavailable."""
        # Local import to avoid pulling the wrapper chain when unused.
        from pykmhelpers.core.seqkit_wrapper import SeqKitWrapper

        try:
            wrapper = SeqKitWrapper()
        except FileNotFoundError:
            return False

        self.engine = "seqkit"
        ok, messages = wrapper.validate(self.filepath, strict=self.strict)
        for msg in messages:
            self._add(0, msg)
        if not ok and not self.errors:
            self._add(0, "seqkit reported the file as invalid")
        return True

    def _validate_builtin(self) -> bool:
        """Validate using the builtin Python checks."""
        self.engine = "builtin"
        try:
            if self.fmt == "fasta":
                self._validate_fasta()
            else:
                self._validate_fastq()
        except Exception as e:
            self._add(0, f"Read error: {e}")
        return not self.errors

    def _add(self, line_num: int, reason: str) -> None:
        if len(self.errors) < self.max_errors:
            self.errors.append((line_num, reason))

    def _invalid_chars(self, line: str) -> str:
        """Return distinct characters not allowed in a sequence line."""
        # set(line) is built in C and holds only distinct chars, so the
        # difference is far cheaper than a per-character Python loop.
        return "".join(sorted(set(line) - self.VALID_SEQ_CHARS))

    def _invalid_qual(self, line: str) -> str:
        """Return distinct characters outside the printable quality range."""
        return "".join(sorted(set(line) - self.VALID_QUAL_CHARS))

    def _validate_fasta(self) -> None:
        with open_sequence_file(self.filepath) as fh:
            header_line = None
            seq_len = 0
            seen_record = False
            for line_num, raw in enumerate(fh, start=1):
                line = raw.rstrip("\r\n")
                if line == "":
                    continue
                if line.startswith(">"):
                    if header_line is not None and seq_len == 0:
                        self._add(header_line, "Header with no sequence")
                    if not line[1:].strip():
                        self._add(line_num, "Empty FASTA header")
                    header_line = line_num
                    seq_len = 0
                    seen_record = True
                else:
                    if header_line is None:
                        self._add(line_num, "Sequence data before any header")
                        continue
                    if self.strict:
                        bad = self._invalid_chars(line)
                        if bad:
                            self._add(line_num, f"Invalid sequence character(s): {bad}")
                    seq_len += len(line)

            if header_line is not None and seq_len == 0:
                self._add(header_line, "Header with no sequence")
            if not seen_record:
                self._add(0, "File contains no FASTA records")

    def _validate_fastq(self) -> None:
        with open_sequence_file(self.filepath) as fh:
            pos = 0  # position within the 4-line record
            seq_len = 0
            record_start = 0
            n_lines = 0
            for line_num, raw in enumerate(fh, start=1):
                n_lines = line_num
                line = raw.rstrip("\r\n")
                if pos == 0:
                    record_start = line_num
                    if not line.startswith("@"):
                        self._add(line_num, "Record header must start with '@'")
                    elif not line[1:].strip():
                        self._add(line_num, "Empty FASTQ header")
                elif pos == 1:
                    seq_len = len(line)
                    if self.strict:
                        bad = self._invalid_chars(line)
                        if bad:
                            self._add(line_num, f"Invalid sequence character(s): {bad}")
                elif pos == 2:
                    if not line.startswith("+"):
                        self._add(line_num, "Separator line must start with '+'")
                else:
                    if len(line) != seq_len:
                        self._add(
                            line_num,
                            f"Quality length ({len(line)}) != sequence length ({seq_len})",
                        )
                    if self.strict:
                        bad = self._invalid_qual(line)
                        if bad:
                            self._add(line_num, f"Invalid quality character(s): {bad}")
                pos = (pos + 1) % 4

            if n_lines == 0:
                self._add(0, "File contains no FASTQ records")
            elif pos != 0:
                self._add(record_start, "Truncated FASTQ record (incomplete 4-line block)")

    def print_errors(self) -> None:
        """Print all validation errors with their line numbers."""
        if not self.errors:
            print(f"No errors found in {self.filepath}")
            return
        print(f"Validation errors in {self.filepath}:")
        for line_num, reason in self.errors:
            print(f"  Line {line_num}: {reason}")

    def get_error_count(self) -> int:
        return len(self.errors)

    def get_errors(self) -> list:
        return self.errors.copy()


def validate_sequence_file(
    filepath,
    fmt: Optional[str] = None,
    use_seqkit: bool = True,
    strict: bool = True,
) -> bool:
    """Convenience helper: return True if the FASTA/FASTQ file is well formed."""
    return SequenceValidator(
        filepath, fmt=fmt, use_seqkit=use_seqkit, strict=strict
    ).validate()


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
