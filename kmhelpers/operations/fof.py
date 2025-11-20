"""
FofManager - Comprehensive manager for file-of-files (fof) operations.

This module provides a centralized interface for all operations related to
kmindex file-of-files format, including reading, writing, validation, and
sample management.
"""

import os
from typing import List, Dict, Tuple, Optional, Union
from pathlib import Path

from ..core.utils import Toolbox, Kmindex


class FofManager:
    """
    Manager class for file-of-files (fof) operations.

    The fof format is used by kmindex to specify input files and their
    associated sample names. Format: "name: path" where name is the sample
    identifier and path is the file path.

    Example:
        >>> manager = FofManager()
        >>> # Create a fof file
        >>> fof_path = manager.create_fof_file(
        ...     input_files=["sample1.fasta.gz", "sample2.fasta.gz"],
        ...     fof_path="samples.fof"
        ... )
        >>> # Load sample IDs
        >>> samples = manager.get_sample_ids(fof_path)
        >>> print(samples)  # ['sample1', 'sample2']
    """

    # Common file extensions for bioinformatics files
    COMMON_EXTENSIONS = [
        ".fasta.gz",
        ".fastq.gz",
        ".fa.gz",
        ".fq.gz",
        ".fna.gz",
        ".fasta",
        ".fastq",
        ".fa",
        ".fq",
        ".fna",
    ]

    def __init__(self):
        """Initialize the FofManager."""
        pass

    @staticmethod
    def parse_fof_line(line: str) -> Optional[Tuple[str, str]]:
        """
        Parse a single line from a fof file.

        Args:
            line: Line to parse in "name: path" format.

        Returns:
            Tuple of (sample_name, file_path) or None if line is empty/invalid.
        """
        line = line.strip()
        if not line:
            return None

        if ":" not in line:
            return None

        parts = line.split(":", 1)
        if len(parts) != 2:
            return None

        sample_name = parts[0].strip()
        file_path = parts[1].strip()

        return (sample_name, file_path)

    @staticmethod
    def extract_sample_name(file_path: Union[str, Path]) -> str:
        """
        Extract sample name from a file path.

        Removes the path and common bioinformatics file extensions to
        derive a clean sample name.

        Args:
            file_path: Path to the file.

        Returns:
            Extracted sample name.

        Example:
            >>> FofManager.extract_sample_name("/path/to/sample_001.fasta.gz")
            'sample_001'
        """
        sample_name = os.path.basename(str(file_path))

        # Remove common extensions in order (compound extensions first)
        for ext in FofManager.COMMON_EXTENSIONS:
            if sample_name.endswith(ext):
                sample_name = sample_name[: -len(ext)]
                break

        return sample_name

    def load_fof_file(self, fof_path: Union[str, Path]) -> List[str]:
        """
        Load sample IDs from a fof file.

        Args:
            fof_path: Path to the fof file.

        Returns:
            Ordered list of sample IDs.

        Raises:
            FileNotFoundError: If fof file doesn't exist.
        """
        fof_path_str = Toolbox.get_canonical_path(str(fof_path))

        if not os.path.exists(fof_path_str):
            raise FileNotFoundError(f"FOF file not found: {fof_path_str}")

        sample_ids = []
        with open(fof_path_str, "r") as f:
            for line in f:
                parsed = self.parse_fof_line(line)
                if parsed:
                    sample_name, _ = parsed
                    sample_ids.append(sample_name)

        return sample_ids

    def load_with_paths(self, fof_path: Union[str, Path]) -> Dict[str, str]:
        """
        Load sample IDs with their associated file paths.

        Args:
            fof_path: Path to the fof file.

        Returns:
            Dictionary mapping sample names to file paths.

        Raises:
            FileNotFoundError: If fof file doesn't exist.
        """
        fof_path_str = Toolbox.get_canonical_path(str(fof_path))

        if not os.path.exists(fof_path_str):
            raise FileNotFoundError(f"FOF file not found: {fof_path_str}")

        sample_map = {}
        with open(fof_path_str, "r") as f:
            for line in f:
                parsed = self.parse_fof_line(line)
                if parsed:
                    sample_name, file_path = parsed
                    sample_map[sample_name] = file_path

        return sample_map

    def get_sample_ids(self, fof_path: Union[str, Path]) -> List[str]:
        """
        Get all sample IDs from a fof file.

        Alias for load_fof_file() for clarity.

        Args:
            fof_path: Path to the fof file.

        Returns:
            List of sample IDs.
        """
        return self.load_fof_file(fof_path)

    def create_fof_file(
        self,
        input_files: List[Union[str, Path]],
        fof_path: Union[str, Path],
        use_absolute_paths: bool = True,
        validate_files: bool = True,
        custom_names: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Create a file-of-files from a list of input files.

        Args:
            input_files: List of input file paths.
            fof_path: Path where the fof file should be created.
            use_absolute_paths: If True, convert all paths to absolute paths.
            validate_files: If True, validate that all input files exist.
            custom_names: Optional dict mapping file paths to custom sample names.
                         If not provided, names are extracted from filenames.

        Returns:
            Absolute path to the created fof file.

        Raises:
            FileNotFoundError: If any input file doesn't exist (when validate_files=True).
        """
        fof_path_str = Toolbox.get_canonical_path(str(fof_path))

        with open(fof_path_str, "w") as f:
            for file_path in input_files:
                file_path_str = str(file_path)

                if use_absolute_paths:
                    file_path_str = Toolbox.get_canonical_path(file_path_str)

                if validate_files and not os.path.exists(file_path_str):
                    raise FileNotFoundError(f"Input file not found: {file_path_str}")

                # Determine sample name
                if custom_names and str(file_path) in custom_names:
                    sample_name = custom_names[str(file_path)]
                else:
                    sample_name = self.extract_sample_name(file_path_str)

                # Write in "name: path" format
                f.write(f"{sample_name}: {file_path_str}\n")

        return fof_path_str

    def validate_fof_file(self, fof_path: Union[str, Path]) -> bool:
        """
        Validate the format and existence of a fof file.

        Args:
            fof_path: Path to the fof file to validate.

        Returns:
            True if file exists and has valid format.

        Raises:
            FileNotFoundError: If fof file doesn't exist.
            ValueError: If fof file has invalid format.
        """
        fof_path_str = Toolbox.get_canonical_path(str(fof_path))

        if not os.path.exists(fof_path_str):
            raise FileNotFoundError(f"FOF file not found: {fof_path_str}")

        line_count = 0
        with open(fof_path_str, "r") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:  # Skip empty lines
                    continue

                line_count += 1
                parsed = self.parse_fof_line(line)
                if parsed is None:
                    raise ValueError(
                        f"Invalid fof format at line {line_num}: '{line}'. "
                        f"Expected format: 'name: path'"
                    )

        if line_count == 0:
            raise ValueError("FOF file is empty")

        return True

    def validate_input_files(
        self, file_list: List[Union[str, Path]], raise_on_missing: bool = True
    ) -> bool:
        """
        Validate that all input files exist.

        Args:
            file_list: List of file paths to validate.
            raise_on_missing: If True, raise FileNotFoundError for missing files.

        Returns:
            True if all files exist.

        Raises:
            FileNotFoundError: If any file is missing (when raise_on_missing=True).
        """
        missing_files = []

        for file_path in file_list:
            file_path_str = str(file_path)
            if not os.path.exists(file_path_str):
                missing_files.append(file_path_str)

        if missing_files:
            if raise_on_missing:
                raise FileNotFoundError(
                    f"Missing input files: {', '.join(missing_files)}"
                )
            return False

        return True

    def validate_samples(
        self, requested_ids: List[str], available_ids: List[str]
    ) -> Tuple[bool, List[str]]:
        """
        Validate that requested sample IDs exist in the available set.

        Args:
            requested_ids: List of requested sample IDs.
            available_ids: List of available sample IDs.

        Returns:
            Tuple of (all_valid: bool, missing_ids: List[str])
        """
        available_set = set(available_ids)
        missing_ids = [sid for sid in requested_ids if sid not in available_set]

        return (len(missing_ids) == 0, missing_ids)

    def is_valid_fof_format(self, line: str) -> bool:
        """
        Check if a line has valid fof format.

        Args:
            line: Line to check.

        Returns:
            True if line has valid "name: path" format.
        """
        return self.parse_fof_line(line) is not None

    @staticmethod
    def get_fof_path(index_dir: Union[str, Path]) -> str:
        """
        Get the standard fof file path within an index directory.

        Args:
            index_dir: Path to the index directory.

        Returns:
            Canonical path to kmtricks.fof file.
        """
        return Kmindex.get_fof_path(str(index_dir))

    def resolve_paths(
        self, fof_path: Union[str, Path], make_absolute: bool = True
    ) -> Dict[str, str]:
        """
        Load all file paths from a fof file and optionally resolve to absolute paths.

        Args:
            fof_path: Path to the fof file.
            make_absolute: If True, convert all paths to absolute paths.

        Returns:
            Dictionary mapping sample names to resolved file paths.
        """
        sample_map = self.load_with_paths(fof_path)

        if make_absolute:
            resolved_map = {}
            for sample_name, file_path in sample_map.items():
                resolved_map[sample_name] = Toolbox.get_canonical_path(file_path)
            return resolved_map

        return sample_map

    def copy_fof(
        self, source_path: Union[str, Path], dest_path: Union[str, Path]
    ) -> str:
        """
        Copy a fof file to a new location.

        Args:
            source_path: Source fof file path.
            dest_path: Destination fof file path.

        Returns:
            Canonical path to the destination file.

        Raises:
            FileNotFoundError: If source file doesn't exist.
        """
        source_str = Toolbox.get_canonical_path(str(source_path))
        dest_str = Toolbox.get_canonical_path(str(dest_path))

        if not os.path.exists(source_str):
            raise FileNotFoundError(f"Source FOF file not found: {source_str}")

        # Read from source and write to destination
        with open(source_str, "r") as src, open(dest_str, "w") as dst:
            dst.write(src.read())

        return dest_str

    def get_file_count(self, fof_path: Union[str, Path]) -> int:
        """
        Get the number of files/samples in a fof file.

        Args:
            fof_path: Path to the fof file.

        Returns:
            Number of samples in the fof file.
        """
        return len(self.load_fof_file(fof_path))

    def append_to_fof(
        self,
        fof_path: Union[str, Path],
        new_files: List[Union[str, Path]],
        use_absolute_paths: bool = True,
        validate_files: bool = True,
    ) -> str:
        """
        Append new files to an existing fof file.

        Args:
            fof_path: Path to the fof file.
            new_files: List of new files to append.
            use_absolute_paths: If True, convert paths to absolute.
            validate_files: If True, validate that files exist.

        Returns:
            Path to the fof file.

        Raises:
            FileNotFoundError: If fof file or any input file doesn't exist.
        """
        fof_path_str = Toolbox.get_canonical_path(str(fof_path))

        if not os.path.exists(fof_path_str):
            raise FileNotFoundError(f"FOF file not found: {fof_path_str}")

        with open(fof_path_str, "a") as f:
            for file_path in new_files:
                file_path_str = str(file_path)

                if use_absolute_paths:
                    file_path_str = Toolbox.get_canonical_path(file_path_str)

                if validate_files and not os.path.exists(file_path_str):
                    raise FileNotFoundError(f"Input file not found: {file_path_str}")

                sample_name = self.extract_sample_name(file_path_str)
                f.write(f"{sample_name}: {file_path_str}\n")

        return fof_path_str
