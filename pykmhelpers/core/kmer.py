import os
import shutil
import subprocess
import tempfile
from .sequence import Sequence


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


class KmerCounter:
    def __init__(self, k: int = 31, threadCount: int = 8):
        if not shutil.which("ntcard"):
            raise FileNotFoundError(
                "ntcard command not found. Please install ntcard and add it to PATH."
            )
        self._k = k
        self._threadCount = threadCount

    @property
    def k(self):
        return self._k

    @property
    def threadCount(self):
        return self._threadCount

    def count(self, filename):
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

    def count_files(self, files):
        """Count k-mers for one or more files in a single ntcard call.

        Args:
            files: List of file paths (fasta, fastq, sam, or bam format)

        Returns:
            int: The F1 value (number of distinct k-mers) from ntcard

        Raises:
            FileNotFoundError: If ntcard fails or files don't exist
            ValueError: If output parsing fails
            subprocess.CalledProcessError: If ntcard execution fails
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

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                raise subprocess.CalledProcessError(
                    result.returncode,
                    result.args,
                    output=result.stdout,
                    stderr=result.stderr,
                )

            # Parse first line from stdout: k=25    F1      96751
            lines = result.stdout.strip().split("\n")
            if not lines:
                raise ValueError("Empty output from ntcard")

            first_line = lines[0]
            parts = first_line.split()

            if len(parts) < 3:
                raise ValueError(f"Unexpected ntcard output format: {first_line}")

            try:
                f1_value = int(parts[2])
            except (ValueError, IndexError) as e:
                raise ValueError(
                    f"Failed to parse F1 value from ntcard output: {first_line}"
                ) from e

            if f1_value == 0:
                raise ValueError(
                    f"No k-mers found (F1=0). Check if files are empty or k={self._k} is larger than sequences."
                )

            return f1_value

        finally:
            if os.path.exists(tmp_file):
                os.remove(tmp_file)

    def count_all(self, samples_dict):
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

            except (FileNotFoundError, ValueError, subprocess.CalledProcessError) as e:
                raise ValueError(
                    f"Error counting k-mers for sample '{sample_name}': {e}"
                ) from e

        return results


