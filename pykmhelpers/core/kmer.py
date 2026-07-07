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
        thread_count: Number of threads passed to ntcard.
        dry_run: If True, commands are built but not executed.
    """

    def __init__(
        self,
        k: int = 31,
        thread_count: int = 8,
        dry_run: bool = False,
    ):
        super().__init__(main_cmd="ntcard", dry_run=dry_run)
        self._k = k
        self._thread_count = thread_count

    @property
    def k(self):
        """K-mer length."""
        return self._k

    @property
    def thread_count(self):
        """Number of threads used by ntcard."""
        return self._thread_count

    def count(
        self, filename: str, mode: KmerCountMode = KmerCountMode.DISTINCT, verbose: bool = False
    ) -> int:
        """Count k-mers in a single file using ntcard.

        Args:
            filename: Path to the sequence file.
            mode: Counting strategy (see KmerCountMode).
            verbose: Print the mode name and resulting value to stdout.

        Returns:
            int: K-mer count extracted from the ntcard histogram according to mode.

        Raises:
            FileNotFoundError: If the sequence file does not exist.
            ValueError: If ntcard produces no output or parsing fails.
            subprocess.SubprocessError: If ntcard returns a non-zero exit code.
        """
        if not os.path.exists(filename):
            raise FileNotFoundError(f"Sequence file not found: {filename}")

        return self.count_files([filename], mode=mode, verbose=verbose)

    def count_files(
        self, files: list, mode: KmerCountMode = KmerCountMode.DISTINCT, verbose: bool = False
    ) -> int:
        """Count k-mers for one or more files in a single ntcard call.

        All files are counted together as a single dataset; use count_all for
        per-sample counting.

        Args:
            files: List of sequence file paths.
            mode: Counting strategy (see KmerCountMode):
                  DISTINCT → F0 (all distinct k-mers),
                  SOLID    → F0 - freq[1] (distinct k-mers appearing at least twice),
                  TOTAL    → F1 (total k-mer occurrences).
            verbose: Print the mode name and resulting value to stdout.

        Returns:
            int: K-mer count extracted from the ntcard histogram according to mode.

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

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as tmp:
            tmp_file = tmp.name

        try:
            cmd = [
                "ntcard",
                "-t",
                str(self._thread_count),
                "-k",
                str(self._k),
                "-o",
                tmp_file,
            ] + files

            result = self._run_cmd(cmd, print_trace=verbose)

            hist_file = f"{tmp_file}_k{self._k}.hist"

            if os.path.exists(hist_file):
                # Old ntcard: "<prefix>_k<k>.hist" with "F1 <n>\nF0 <n>\n1 <n>\n..."
                with open(hist_file) as f:
                    lines = f.read().strip().split("\n")

                if len(lines) < 2:
                    raise ValueError("Unexpected ntcard output format")

                def parse_hist_line(line):
                    parts = line.split()
                    if len(parts) < 2:
                        raise ValueError(f"Cannot parse ntcard output line: {line!r}")
                    return int(parts[1])

                if mode == KmerCountMode.DISTINCT:
                    value = parse_hist_line(lines[1])  # F0
                elif mode == KmerCountMode.SOLID:
                    freq1 = parse_hist_line(lines[2]) if len(lines) > 2 else 0
                    value = parse_hist_line(lines[1]) - freq1  # F0 - freq[1]
                else:  # TOTAL
                    value = parse_hist_line(lines[0])  # F1

            elif os.path.getsize(tmp_file) > 0:
                # New ntcard: output written directly to "-o" path as TSV "k\tf\tn"
                # F0/F1 summary also available on stderr as "k=<k>\t<stat>\t<value>"
                with open(tmp_file) as f:
                    lines = f.read().strip().split("\n")

                freq: dict[int, int] = {}
                for line in lines[1:]:  # skip header "k  f  n"
                    parts = line.split()
                    if len(parts) >= 3:
                        try:
                            freq[int(parts[1])] = int(parts[2])
                        except ValueError:
                            pass

                f0 = sum(freq.values())
                freq1 = freq.get(1, 0)

                f1: int | None = None
                for line in result.stderr.splitlines():
                    parts = line.split()
                    if (
                        len(parts) >= 3
                        and parts[0].startswith("k=")
                        and parts[1] == "F1"
                    ):
                        try:
                            f1 = int(parts[2])
                        except ValueError:
                            pass

                if mode == KmerCountMode.DISTINCT:
                    value = f0
                elif mode == KmerCountMode.SOLID:
                    value = f0 - freq1
                else:  # TOTAL
                    value = f1 or 0

            else:
                raise ValueError("ntcard produced no output")

            if verbose:
                print(f"{mode.name}={value}")

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

    def count_all(
        self, samples_dict: dict, mode: KmerCountMode = KmerCountMode.DISTINCT, verbose: bool = False
    ) -> dict:
        """Count k-mers for multiple samples.

        Samples that already contain a "kmer_count" key are skipped.

        Args:
            samples_dict: Dictionary mapping sample names to their metadata::

                {
                    "sample_name": {"files": [list of file paths], ...},
                    ...
                }

            mode: Counting strategy applied to every sample (see KmerCountMode).
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
                kmer_count = self.count_files(files, mode=mode, verbose=verbose)
                results[sample_name] = kmer_count

            except (FileNotFoundError, ValueError, subprocess.SubprocessError) as e:
                raise ValueError(
                    f"Error counting k-mers for sample '{sample_name}': {e}"
                ) from e

        return results
