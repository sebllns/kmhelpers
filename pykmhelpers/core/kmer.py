import os
import subprocess
import tempfile
from enum import Enum

from pykmhelpers.core.sequence import Sequence
from pykmhelpers.core.wrapper import Wrapper


class Kmer(Sequence):
    """A k-mer sequence with a fixed length k."""

    def __init__(self, seq: str, k: int = 0, header: str = ""):
        if k == 0:
            k = len(seq)
        if len(seq) != k:
            raise ValueError(f"Sequence length {len(seq)} doesn't match k={k}")
        super().__init__(content=seq, header=header)
        self._k = k

    @property
    def k(self):
        return self._k


class KmerCountMode(Enum):
    """Counting strategy returned by KmerCounter.

    DISTINCT: all distinct k-mers; suited for assembled sequences.
    SOLID:    distinct k-mers appearing at least twice;
              filters sequencing errors from raw reads.
    TOTAL:    total k-mer occurrences across all reads.
    """

    DISTINCT = 0
    SOLID = 1
    TOTAL = 2


# Accepted input formats: fasta, fastq, sam, bam (plain or compressed gz, bz2, zip, xz).
# A file listing input paths one per line can also be passed with a '@' prefix.
class KmerCounter(Wrapper):
    """Wrapper around ntcard for counting k-mers in sequence files.

    Args:
        k: K-mer length.
        threadCount: Number of threads passed to ntcard.
        mode: Counting strategy; determines which value is extracted from the
              ntcard histogram (see KmerCountMode).
        dry_run: If True, commands are built but not executed.
    """

    def __init__(
        self,
        k: int = 31,
        threadCount: int = 8,
        mode: KmerCountMode = KmerCountMode.DISTINCT,
        dry_run: bool = False,
    ):
        super().__init__(main_cmd="ntcard", dry_run=dry_run)
        self._k = k
        self._threadCount = threadCount
        self._mode = mode

    @property
    def k(self):
        """K-mer length."""
        return self._k

    @property
    def threadCount(self):
        """Number of threads used by ntcard."""
        return self._threadCount

    @property
    def mode(self):
        """Counting strategy applied when reading the ntcard histogram."""
        return self._mode

    def count(self, filename, verbose=False):
        """Count k-mers in a single file using ntcard.

        Args:
            filename: Path to the sequence file.
            verbose: Print the mode name and resulting value to stdout.

        Returns:
            int: K-mer count extracted from the ntcard histogram according to self.mode.

        Raises:
            FileNotFoundError: If the sequence file does not exist.
            ValueError: If ntcard produces no output or parsing fails.
            subprocess.SubprocessError: If ntcard returns a non-zero exit code.
        """
        if not os.path.exists(filename):
            raise FileNotFoundError(f"Sequence file not found: {filename}")

        return self.count_files([filename], verbose=verbose)

    def count_files(self, files, verbose=False):
        """Count k-mers for one or more files in a single ntcard call.

        All files are counted together as a single dataset; use count_all for
        per-sample counting.

        Args:
            files: List of sequence file paths.
            verbose: Print the mode name and resulting value to stdout.

        Returns:
            int: K-mer count extracted from the ntcard histogram according to self.mode:
                 DISTINCT → F0 (all distinct k-mers),
                 SOLID    → F0 - freq[1] (distinct k-mers appearing at least twice),
                 TOTAL    → F1 (total k-mer occurrences).

        Raises:
            FileNotFoundError: If any input file does not exist.
            ValueError: If ntcard produces no output or parsing fails.
            subprocess.SubprocessError: If ntcard returns a non-zero exit code.
        """
        if not files:
            raise ValueError("At least one file is required")

        for file_path in files:
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File not found: {file_path}")

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as tmp:
            tmp_file = tmp.name

        try:
            cmd = [
                "ntcard",
                "-t",
                str(self._threadCount),
                "-k",
                str(self._k),
                "-o",
                tmp_file,
            ] + files

            self._run_cmd(cmd, print_trace=verbose)

            hist_file = f"{tmp_file}_k{self._k}.hist"
            if not os.path.exists(hist_file):
                raise ValueError(f"ntcard output file not found: {hist_file}")

            with open(hist_file) as f:
                lines = f.read().strip().split("\n")

            if len(lines) < 2:
                raise ValueError("Unexpected ntcard output format")

            def parse_line(line):
                parts = line.split()
                if len(parts) < 2:
                    raise ValueError(f"Cannot parse ntcard output line: {line!r}")
                return int(parts[1])

            if self._mode == KmerCountMode.DISTINCT:
                value = parse_line(lines[1])  # F0
            elif self._mode == KmerCountMode.SOLID:
                freq1 = parse_line(lines[2]) if len(lines) > 2 else 0
                value = parse_line(lines[1]) - freq1  # F0 - freq[1]
            else:  # TOTAL
                value = parse_line(lines[0])  # F1

            if verbose:
                print(f"{self._mode.name}={value}")

            if value == 0:
                raise ValueError(
                    f"No k-mers found. Check if files are empty or k={self._k} is larger than sequences."
                )

            return value

        finally:
            hist_file = f"{tmp_file}_k{self._k}.hist"
            for path in (tmp_file, hist_file):
                if os.path.exists(path):
                    os.remove(path)

    def count_all(self, samples_dict, verbose=False):
        """Count k-mers for multiple samples.

        Samples that already contain a "kmer_count" key are skipped.

        Args:
            samples_dict: Dictionary mapping sample names to their metadata::

                {
                    "sample_name": {"files": [list of file paths], ...},
                    ...
                }

            verbose: Forward verbosity to each count_files call.

        Returns:
            dict[str, int]: K-mer count per sample name.

        Raises:
            ValueError: If a sample entry is malformed or ntcard fails.
        """
        results = {}

        for sample_name, sample_data in samples_dict.items():
            if not isinstance(sample_data, dict) or "files" not in sample_data:
                raise ValueError(
                    f"Invalid sample format for '{sample_name}': must have 'files' key"
                )

            if "kmer_count" in sample_data:
                continue

            files = sample_data["files"]
            if not isinstance(files, list):
                raise ValueError(
                    f"Invalid files format for '{sample_name}': 'files' must be a list"
                )

            if not files:
                raise ValueError(f"No files specified for sample '{sample_name}'")

            try:
                kmer_count = self.count_files(files, verbose=verbose)
                results[sample_name] = kmer_count

            except (FileNotFoundError, ValueError, subprocess.SubprocessError) as e:
                raise ValueError(
                    f"Error counting k-mers for sample '{sample_name}': {e}"
                ) from e

        return results
