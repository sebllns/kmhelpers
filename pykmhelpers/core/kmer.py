import os
import subprocess
import tempfile

from .sequence import Sequence
from .wrapper import Wrapper


class Kmer(Sequence):

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


class KmerCounter(Wrapper):
    def __init__(self, k: int = 31, threadCount: int = 8, dry_run: bool = False):
        super().__init__(main_cmd="ntcard", dry_run=dry_run)
        self._k = k
        self._threadCount = threadCount

    @property
    def k(self):
        return self._k

    @property
    def threadCount(self):
        return self._threadCount

    def count(self, filename, verbose=False):
        """Count k-mers in a single file using ntcard.

        Args:
            filename: Path to the sequence file (fasta, fastq, sam, or bam)

        Returns:
            int: The F1 value (number of distinct k-mers) from ntcard

        Raises:
            FileNotFoundError: If ntcard is not installed or filename doesn't exist
            ValueError: If output parsing fails
            subprocess.CalledProcessError: If ntcard execution fails
        """
        if not os.path.exists(filename):
            raise FileNotFoundError(f"Sequence file not found: {filename}")

        return self.count_files([filename])

    def count_files(self, files, target_value="F0", verbose=False):
        """Count k-mers for one or more files in a single ntcard call.

        Args:
            files: List of file paths (fasta, fastq, sam, or bam format)

        Returns:
            int: The F1 value (number of distinct k-mers) from ntcard

        Raises:
            FileNotFoundError: If ntcard fails or files don't exist
            ValueError: If output parsing fails
            subprocess.SubprocessError: If ntcard execution fails
        """
        if not files:
            raise ValueError("At least one file is required")

        # Verify all files exist
        for file_path in files:
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File not found: {file_path}")

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as tmp:
            tmp_file = tmp.name

        try:
            # Build command: ntcard -t <threads> -k <k> -o <output> file1 file2 ...
            cmd = [
                "ntcard",
                "-t",
                str(self._threadCount),
                "-k",
                str(self._k),
                "-o",
                tmp_file,
            ] + files

            result = self._run_cmd(cmd, print_trace=verbose)

            # Parse first line from stdout: k=25    F1      96751
            lines = result.stderr.strip().split("\n")
            if not lines:
                raise ValueError("Empty output from ntcard")

            value = 0

            for line in lines:
                try:
                    parts = line.split()
                    if len(parts) >= 3 and target_value == parts[1]:
                        value = int(parts[2])
                        break
                except:
                    pass

            if verbose:
                print(f"{target_value}={value}")

            if value == 0:
                raise ValueError(
                    f"No k-mers found (F1=0). Check if files are empty or k={self._k} is larger than sequences."
                )

            return value

        finally:
            if os.path.exists(tmp_file):
                os.remove(tmp_file)

    def count_all(self, samples_dict, verbose=False):
        """Count k-mers for multiple samples from a dictionary.

        Args:
            samples_dict: Dictionary with structure:
                {
                    "sample_name": {"files": [list of file paths]},
                    ...
                }

        Returns:
            dict: Results with structure:
                {
                    "sample_name": {"kmer_count": count, "files": [file list]},
                    ...
                }

        Raises:
            ValueError: If sample dictionary is malformed
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
                # Count k-mers for all files in a single ntcard call
                f1_value = self.count_files(files)

                results[sample_name] = f1_value

            except (FileNotFoundError, ValueError, subprocess.SubprocessError) as e:
                raise ValueError(
                    f"Error counting k-mers for sample '{sample_name}': {e}"
                ) from e

        return results
