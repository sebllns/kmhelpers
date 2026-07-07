"""
FofManager - Comprehensive manager for file-of-files (fof) operations.

This module provides a centralized interface for all operations related to
kmindex file-of-files format, including reading, writing, validation, and
sample management.
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union

from pykmhelpers.core.index import get_fof_path
from pykmhelpers.core.utils import Toolbox


class FofManager:
    """
    Manager class for file-of-files (fof) operations.

    The fof format is used by kmindex to specify input files and their
    associated sample names. Format: "name: path" where name is the sample
    identifier and path is the file path.

    FofManager maintains an internal dictionary (samples: Dict[str, str])
    mapping sample IDs to file paths, allowing in-memory management of the
    fof data before saving to disk.

    Attributes:
        samples: Dictionary mapping sample IDs to file paths.

    Example:
        >>> # Load and manage a fof file
        >>> manager = FofManager("samples.fof")
        >>> print(manager.get_sample_count())  # Number of samples
        >>>
        >>> # Modify samples in memory
        >>> manager.add_sample("new_sample", "/path/to/new_sample.fasta.gz")
        >>> manager.remove_sample("old_sample")
        >>>
        >>> # Save changes to file
        >>> manager.save("updated_samples.fof")
        >>>
        >>> # Create a new fof from scratch
        >>> manager = FofManager()
        >>> manager.add_sample("sample1", "sample1.fasta.gz")
        >>> manager.add_sample("sample2", "sample2.fasta.gz")
        >>> manager.save("new_samples.fof")
        >>>
        >>> # Or use static methods for one-off operations
        >>> fof_path = FofManager.create_fof_file(
        ...     input_files=["sample1.fasta.gz", "sample2.fasta.gz"],
        ...     fof_path="samples.fof"
        ... )
    """

    # Common file extensions for bioinformatics files
    # Move this into common or utils
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

    def __init__(
        self,
        fof_path: Optional[Union[str, Path]] = None,
        samples: Optional[Dict[str, str]] = None,
    ):
        """
        Initialize the FofManager.

        Args:
            fof_path: Optional path to a fof file to load initially.
                     If provided, the samples dict will be populated from this file.
        """
        self.samples: Dict[str, str] = samples if samples else {}

        if fof_path:
            self.load(fof_path)

    def list_files_in_directory(
        self,
        directory: Union[str, Path],
        recursive: bool = False,
        extensions: Optional[List[str]] = None,
    ) -> List[str]:
        """
        List all files in a directory matching common bioinformatics extensions.

        Args:
            directory: Directory path to search.
            recursive: If True, search recursively in subdirectories.
            extensions: List of extensions to filter by. If None, uses COMMON_EXTENSIONS.

        Returns:
            List of file paths matching the extensions.

        Raises:
            NotADirectoryError: If directory doesn't exist or is not a directory.
        """
        directory_str = Toolbox.get_canonical_path(str(directory))

        if not os.path.exists(directory_str):
            raise NotADirectoryError(f"Directory not found: {directory_str}")

        if not os.path.isdir(directory_str):
            raise NotADirectoryError(f"Path is not a directory: {directory_str}")

        if extensions is None:
            extensions = self.COMMON_EXTENSIONS

        matched_files = []

        if recursive:
            for root, _, files in os.walk(directory_str):
                for filename in files:
                    if any(filename.endswith(ext) for ext in extensions):
                        matched_files.append(os.path.join(root, filename))
        else:
            for item in os.listdir(directory_str):
                item_path = os.path.join(directory_str, item)
                if os.path.isfile(item_path):
                    if any(item.endswith(ext) for ext in extensions):
                        matched_files.append(item_path)

        # Sort for consistent ordering
        matched_files.sort()

        return matched_files

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

    def extract_sample_name(
        self, file_path: Union[str, Path], add_id: bool = False, prefix: str = ""
    ) -> str:
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

        """
        Clean sample_id by:
        1. Replace special characters (non-alphanumeric except underscore) with underscore
        2. Remove duplicate consecutive underscores
        3. Remove leading underscores
        """
        # Replace special characters with underscore
        sample_name = re.sub(r"[^a-zA-Z0-9_]", "_", sample_name)

        # Remove duplicate consecutive underscores
        sample_name = re.sub(r"_+", "_", sample_name)

        # Remove leading underscores
        sample_name = sample_name.lstrip("_")

        if prefix:
            sample_name = prefix + "_" + sample_name

        if add_id:
            sample_name = "{:06d}".format(self.get_sample_count()) + sample_name

        return sample_name

    def load(self, fof_path: Union[str, Path]) -> None:
        """
        Load a fof file and populate the internal samples dictionary.

        Args:
            fof_path: Path to the fof file.

        Raises:
            FileNotFoundError: If fof file doesn't exist.
        """
        self.samples = self.load_with_paths(fof_path)

    def load_from_files(
        self,
        input_files: Sequence[Union[str, Path]],
        use_absolute_paths: bool = True,
        validate_files: bool = True,
        replace_existing: bool = False,
        custom_names: Optional[Sequence[str]] = None,
    ) -> None:
        """
        Load samples from a list of input files into the internal dictionary.

        Args:
            input_files: List of input file paths.
            use_absolute_paths: If True, convert all paths to absolute paths.
            validate_files: If True, validate that all input files exist.
            custom_names: Optional dict mapping file paths to custom sample names.

        Raises:
            FileNotFoundError: If any input file doesn't exist (when validate_files=True).
        """
        self.samples.clear()

        for idx, file_path in enumerate(input_files):
            file_path_str = str(file_path)

            if use_absolute_paths:
                file_path_str = Toolbox.get_canonical_path(file_path_str)

            if validate_files and not os.path.exists(file_path_str):
                print(f"[Warning] Skipping file not found: {file_path_str}")

            # Determine sample name
            sample_name = (
                custom_names[idx]
                if custom_names and idx < len(custom_names)
                else self.extract_sample_name(file_path_str)
            )

            if not self.has_sample(sample_name) or replace_existing:
                self.add_sample([file_path_str], sample_name)

    def load_from_directory(
        self,
        directory: Union[str, Path],
        recursive: bool = False,
        extensions: Optional[List[str]] = None,
        use_absolute_paths: bool = True,
    ) -> None:
        """
        Load samples from all matching files in a directory into the internal dictionary.

        Args:
            directory: Directory containing input files.
            recursive: If True, search recursively in subdirectories.
            extensions: List of extensions to filter by. If None, uses COMMON_EXTENSIONS.
            use_absolute_paths: If True, convert all paths to absolute paths.

        Raises:
            NotADirectoryError: If directory doesn't exist or is not a directory.
            ValueError: If no matching files found in directory.
        """
        input_files = self.list_files_in_directory(
            directory=directory, recursive=recursive, extensions=extensions
        )

        if not input_files:
            ext_list = ", ".join(extensions if extensions else self.COMMON_EXTENSIONS)
            raise ValueError(
                f"No files with extensions [{ext_list}] found in directory: {directory}"
            )

        self.load_from_files(
            input_files=input_files,
            use_absolute_paths=use_absolute_paths,
            validate_files=True,
        )

    def clear(self) -> None:
        """Clear the internal samples dictionary."""
        self.samples.clear()

    def add_sample(self, path: list[str], sample_id: str = "") -> None:
        """
        Add or update a sample in the internal dictionary.

        Args:
            sample_id: Sample identifier.
            path: File path for the sample.
        """
        self.samples[sample_id if sample_id else self.extract_sample_name(path[0])] = (
            ";".join(path)
        )

    def remove_sample(self, sample_id: str) -> bool:
        """
        Remove a sample from the internal dictionary.

        Args:
            sample_id: Sample identifier to remove.

        Returns:
            True if sample was removed, False if it didn't exist.
        """
        if sample_id in self.samples:
            del self.samples[sample_id]
            return True
        return False

    def get_sample_path_str(self, sample_id: str) -> Optional[str]:
        """
        Get the file path for a sample.

        Args:
            sample_id: Sample identifier.

        Returns:
            File path if sample exists, None otherwise.
        """
        return self.samples.get(sample_id)

    def split_path(self, path_list: str) -> list[str]:
        return path_list.split(";")

    def get_sample_paths(self, sample_id: str) -> Optional[list[str]]:
        """
        Get the file path for a sample.

        Args:
            sample_id: Sample identifier.

        Returns:
            File path if sample exists, None otherwise.
        """
        if sample_id in self.samples:
            return self.split_path(self.samples[sample_id])

    def has_sample(self, sample_id: str) -> bool:
        """
        Check if a sample exists in the internal dictionary.

        Args:
            sample_id: Sample identifier.

        Returns:
            True if sample exists.
        """
        return sample_id in self.samples

    def get_all_sample_ids(self) -> List[str]:
        """
        Get all sample IDs from the internal dictionary.

        Returns:
            List of sample IDs in insertion order.
        """
        return list(self.samples.keys())

    def get_all_paths(self) -> List[str]:
        """
        Get all file paths from the internal dictionary.

        Returns:
            List of file paths in insertion order.
        """
        return list(self.samples.values())

    def get_sample_count(self) -> int:
        """
        Get the number of samples in the internal dictionary.

        Returns:
            Number of samples.
        """
        return len(self.samples)

    def save(self, fof_path: Union[str, Path], use_absolute_paths: bool = False) -> str:
        """
        Save the internal samples dictionary to a fof file.

        Args:
            fof_path: Path where the fof file should be created.
            use_absolute_paths: If True, convert all paths to absolute paths.

        Returns:
            Absolute path to the created fof file.
        """
        fof_path_str = Toolbox.get_canonical_path(str(fof_path))

        with open(fof_path_str, "w") as f:
            for sample_id, file_path in self.samples.items():
                output_path = file_path
                if use_absolute_paths:
                    output_path = Toolbox.get_canonical_path(file_path)
                f.write(f"{sample_id}: {output_path}\n")

        return fof_path_str

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
                    sample_map[sample_name] = Toolbox.get_canonical_path(file_path)

        return sample_map

    def validate_sample_files(self) -> bool:
        ok = self.get_sample_count() > 0
        for k, v in self.samples.items():
            for p in self.split_path(v):
                if not os.path.isfile(p):
                    print(f"Sample: {k}\nFile not found: {p}")
                    ok = False
        return ok

    def validate_fof_format(self, fof_path: Union[str, Path]) -> bool:
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

    @staticmethod
    def get_fof_path(index_dir: Union[str, Path]) -> str:
        """
        Get the standard fof file path within an index directory.

        Args:
            index_dir: Path to the index directory.

        Returns:
            Canonical path to kmtricks.fof file.
        """
        return get_fof_path(str(index_dir))
