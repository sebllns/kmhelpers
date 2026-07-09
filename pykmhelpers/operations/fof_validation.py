#!/usr/bin/env python3
"""
FOF (File of Files) Format Validator

This module provides validation for FOF files used by kmtricks/kmindex.

FOF Format Specification:
========================

The FOF format is used to specify sample data for k-mer counting and analysis.
Each line defines a sample with its associated files and optional parameters.

Format:
    <sample_id> : <file_paths> [! <abundance_threshold>]

Where:
    - sample_id: Unique identifier (alphanumeric, underscore, hyphen)
    - file_paths: One or more paths separated by semicolons
    - abundance_threshold: Optional per-sample k-mer abundance minimum (defaults to global --hard-min)

Example FOF file:
    D1 : /path/to/D1.fasta ! 20
    D2 : /path/to/D2.fasta ; /path/to/D2_R2.fasta ! 15
    D3 : ./relative/path.fa
    sample_4 : file1.fa; file2.fa

The abundance threshold (number after !) allows per-sample control of k-mer filtering:
    - If 0 or omitted: The global --hard-min CLI parameter value is used
    - If > 0: This sample-specific threshold overrides the global setting

This provides fine-grained control where different samples can have different
minimum abundance thresholds for k-mer filtering during counting/merging.

Validation Rules:
=================

1. Sample ID: Must match [A-Za-z0-9_-]+
   - Valid: sample1, S_1, s-1
   - Invalid: sample,1 (contains comma), sample=1 (invalid char)

2. File paths: Must match [.A-Za-z0-9\\/_\\-; ]+
   - Valid: /path/to/file.txt, ./relative/path.fa, file1.fa; file2.fa
   - Invalid: /path/to/{file}.txt (contains braces)

3. Forbidden characters: < > { } , [ ]
   - These characters are not allowed anywhere in the line

4. Abundance threshold: Optional unsigned integer after !
   - Valid: ! 20, ! 100 (Override the global --hard-min value)
   - Valid (omitted): line without ! (Use the global --hard-min value)

5. Sample IDs must be unique
   - Duplicate IDs are not allowed
"""

import logging
import re
from typing import List, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


class FofValidator:
    """
    Validates FOF (File of Files) format files.

    This class checks that FOF files respect the format specification and reports
    validation errors with detailed information about invalid lines.

    The FOF format is used by kmtricks/kmindex to specify sample data for k-mer
    counting and analysis operations.

    Attributes:
        file_path (Path): Path to the FOF file to validate
        pattern (re.Pattern): Regex pattern for valid FOF format
        invalid_chars_pattern (re.Pattern): Regex pattern for detecting forbidden characters

    Example:
        >>> validator = FofValidator('samples.fof')
        >>> is_valid = validator.validate()
        >>> if not is_valid:
        ...     validator.print_errors()
    """

    # Regex pattern for valid FOF format:
    # Group 1: Sample ID [A-Za-z0-9_-]+
    # Group 2: File paths [.A-Za-z0-9\/_\-; ]+
    # Group 3: Optional whitespace and ! marker (optional)
    # Group 4: Optional abundance threshold number (optional)
    PATTERN = re.compile(
        r"(^[A-Za-z0-9_-]+)[\s]*:[\s]*([.A-Za-z0-9\/_\-; ]+)([\s]*![\s]*)?"
        r"([0-9]+$)?"
    )

    # Regex pattern for forbidden characters: < > { } , [ ]
    INVALID_CHARS = re.compile(r"([<>{},\[\]])")

    def __init__(self, file_path: str):
        """
        Initialize the FOF validator.

        Args:
            file_path (str): Path to the FOF file to validate

        Raises:
            FileNotFoundError: If the file does not exist
        """
        self.file_path = Path(file_path)
        if not self.file_path.exists():
            raise FileNotFoundError(f"FOF file not found: {self.file_path}")

        self.errors: List[Tuple[int, str, str]] = []
        self.sample_ids: set = set()

    def validate(self) -> bool:
        """
        Validate the FOF file.

        Returns:
            bool: True if the file is valid, False otherwise
        """
        self.errors = []
        self.sample_ids = set()

        try:
            with open(self.file_path, 'r') as f:
                for line_num, line in enumerate(f, start=1):
                    self._validate_line(line_num, line)
        except Exception as e:
            self.errors.append((0, f"File read error", str(e)))
            return False

        return not self.errors

    def _validate_line(self, line_num: int, line: str) -> None:
        """
        Validate a single line from the FOF file.

        Args:
            line_num (int): Line number (1-based)
            line (str): The line content to validate
        """
        # Strip whitespace
        stripped = line.rstrip('\n').strip()

        # Skip empty lines
        if not stripped:
            return

        # Check for forbidden characters
        invalid_match = self.INVALID_CHARS.search(line)
        if invalid_match:
            char = invalid_match.group(1)
            self.errors.append(
                (line_num, f"Invalid character '{char}'", stripped)
            )
            return

        # Check format matches pattern
        format_match = self.PATTERN.match(stripped)
        if not format_match:
            self.errors.append(
                (line_num, "Invalid FOF format", stripped)
            )
            return

        # Extract sample ID
        sample_id = format_match.group(1)

        # Check for duplicate sample IDs
        if sample_id in self.sample_ids:
            self.errors.append(
                (line_num, f"Duplicate sample ID: {sample_id}", stripped)
            )
        else:
            self.sample_ids.add(sample_id)

    def print_errors(self) -> None:
        """
        Print all validation errors in a formatted way.

        Displays each error with line number, reason, and the problematic line content.
        """
        if not self.errors:
            logger.info("No errors found.")
            return

        logger.info(f"Validation errors in {self.file_path}:")

        for line_num, reason, line_content in self.errors:
            logger.info(f"Line {line_num}: {reason}")
            logger.info(f"  > {line_content}")

    def get_error_count(self) -> int:
        """
        Get the number of validation errors.

        Returns:
            int: Number of errors found
        """
        return len(self.errors)

    def get_errors(self) -> List[Tuple[int, str, str]]:
        """
        Get all validation errors.

        Returns:
            List[Tuple[int, str, str]]: List of (line_num, reason, line_content) tuples
        """
        return self.errors.copy()


def main():
    """Example usage of the FofValidator class."""
    import sys

    if len(sys.argv) < 2:
        logger.error("Usage: python fof_validation.py <fof_file>")
        sys.exit(1)

    fof_file = sys.argv[1]

    try:
        validator = FofValidator(fof_file)
        is_valid = validator.validate()

        if is_valid:
            logger.info(f"{fof_file} is valid")
            sys.exit(0)
        else:
            logger.error(f"{fof_file} has {validator.get_error_count()} error(s):")
            validator.print_errors()
            sys.exit(1)

    except FileNotFoundError as e:
        logger.error(f"{e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
