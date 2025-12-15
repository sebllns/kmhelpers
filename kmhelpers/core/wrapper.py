"""
KmindexWrapper - High-level interface for kmindex build and query operations.
"""

import os
import subprocess
from typing import List, Optional, Union
from pathlib import Path

from .utils import Bin, Toolbox, Kmindex
from ..operations.fof import FofManager


class KmindexWrapper:
    """
    High-level wrapper class for kmindex operations.

    This class provides a convenient interface for building and querying kmindex indices.
    It handles command construction, parameter validation, and integrates with the
    existing kmhelpers infrastructure.

    Example:
        >>> wrapper = KmindexWrapper()
        >>> index = wrapper.build(
        ...     index_path="my_index",
        ...     input_files=["sample1.fasta.gz", "sample2.fasta.gz"],
        ...     kmer_size=31,
        ...     bloom_size=10000000
        ... )
        >>> results_dir = wrapper.query(
        ...     index="my_index",
        ...     query_file="query.fasta",
        ...     output_dir="results"
        ... )
    """

    def __init__(self):
        """Initialize the KmindexWrapper."""
        self._fof_manager = FofManager()

    @property
    def fof_manager(self):
        return self._fof_manager

    def build(
        self,
        input_fof_file: Optional[Union[str, Path]],
        output_registry_path: Union[str, Path],
        output_index_dir: Optional[Union[str, Path]] = None,
        k: int = 31,
        minim_size: int = 10,
        bloom_size: Optional[int] = None,
        nb_cell: Optional[int] = None,
        bitw: int = 2,
        hard_min: int = 2,
        nb_partitions: int = 0,
        threads: int = 1,
        compress_intermediate: bool = False,
        register_as: Optional[str] = None,
        from_index: Optional[str] = None,
        km_path: Optional[Union[str, Path]] = None,
        verbose: str = "info",
    ) -> None:
        """
        Build a kmindex index.

        Args:
            input_fof_file: Path to file-of-filenames containing input FASTA/FASTQ files.
            output_registry_path: Path to the registry directory where index.json will be created/updated.
            output_index_dir: Optional custom directory name for the index. If None, uses register_as value.
            k: K-mer size (8-255).
            minim_size: Minimizer size (4-15).
            bloom_size: Bloom filter size in bits for presence/absence indexing (total number of bit positions).
            nb_cell: Number of cells in counting Bloom filter for abundance indexing (mutually exclusive with bloom_size).
            bitw: Bits per cell for abundance indexing (creates 2^bitw classes).
            hard_min: Minimum k-mer abundance threshold.
            nb_partitions: Number of partitions (0=auto).
            threads: Number of threads.
            compress_intermediate: Whether to compress intermediate files (--cpr flag).
            register_as: Index name for registration. If None, derived from output_index_dir or fof filename.
            from_index: Use parameters from a pre-registered index.
            km_path: Path to kmtricks binary (if not in $PATH).
            verbose: Verbosity level (debug|info|warning|error).

        Returns:
            KmtricksIndex object representing the built index.

        Raises:
            ValueError: If both bloom_size and nb_cell are specified.
            FileNotFoundError: If input_fof_file doesn't exist.
            subprocess.CalledProcessError: If kmindex build command fails.
        """
        # Validate inputs
        if bloom_size is not None and nb_cell is not None:
            raise ValueError(
                "bloom_size and nb_cell are mutually exclusive. "
                "Use bloom_size for presence/absence indexing or nb_cell for abundance indexing."
            )

        # Handle fof file creation if input_files provided
        input_fof_file = Toolbox.get_canonical_path(str(input_fof_file))
        if not os.path.exists(input_fof_file):
            raise FileNotFoundError(f"File-of-filenames not found: {input_fof_file}")

        output_registry_path = Toolbox.get_canonical_path(str(output_registry_path))

        # Set default register_as if not provided (required parameter)
        if register_as is None:
            register_as = os.path.splitext(os.path.basename(input_fof_file))[0]

        # Set default run_dir if not provided (required parameter)
        if output_index_dir is None:
            output_index_dir = os.path.join(
                os.path.dirname(output_registry_path), ".subindexes", register_as
            )

        output_index_dir = Toolbox.get_canonical_path(str(output_index_dir))

        if os.path.exists(output_index_dir):
            raise FileExistsError(
                f"run_dir directory already exists: {output_index_dir}"
            )

        os.makedirs(os.path.dirname(output_index_dir), exist_ok=True)

        # Build command
        cmd = [
            Bin.kmindex(),
            "build",
            "--index",
            output_registry_path,
            "--fof",
            input_fof_file,
            "--run-dir",
            output_index_dir,
            "--register-as",
            register_as,
            "--kmer-size",
            str(k),
            "--minim-size",
            str(minim_size),
            "--hard-min",
            str(hard_min),
            "--nb-partitions",
            str(nb_partitions),
            "--threads",
            str(threads),
            "--verbose",
            verbose,
        ]

        # Add indexing type parameters
        if bloom_size is not None:
            cmd.extend(["--bloom-size", str(bloom_size)])
        elif nb_cell is not None:
            cmd.extend(["--nb-cell", str(nb_cell), "--bitw", str(bitw)])
        else:
            raise ValueError(
                "Either bloom_size (for presence/absence) or nb_cell (for abundance) must be specified"
            )

        # Add optional parameters
        if compress_intermediate:
            cmd.append("--cpr")

        if from_index is not None:
            cmd.extend(["--from", from_index])

        if km_path is not None:
            cmd.extend(["--km-path", str(km_path)])

        # Print command for debugging
        print("Executing command:")
        print(" ".join(cmd))

        # Execute command
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            print(result.stdout)
            if result.stderr:
                print(result.stderr)
        except subprocess.CalledProcessError as e:
            print(f"Error building index: {e.stderr}")
            raise

        # Return KmtricksIndex object
        # For a newly built index, the index is at index_path and we need to extract
        # the parent directory and index name
        parent_dir = os.path.dirname(output_registry_path)
        index_name = os.path.basename(output_registry_path)

        # If parent_dir is empty (relative path), use current directory
        if not parent_dir:
            parent_dir = os.getcwd()

    def query(
        self,
        input_registry: str,
        query_file: str,
        output_dir: str = "query_results",
        names: Optional[List[str]] = None,
        format: str = "json",
        zvalue: int = 0,
        threshold: float = 0.0,
        monitor: bool = False,
        is_compressed: bool = False,
    ) -> None:
        """
        Query a kmindex index.

        This method wraps the existing Kmindex.query_index() functionality.

        Args:
            index: Path to index directory or KmtricksIndex object.
            query_file: Path to query FASTA/FASTQ file.
            output_dir: Path to output directory (must not exist).
            names:  Sub-indexes to query, comma separated. {all}
            format: Output format (e.g., "json").
            fastx: Input fasta/q file (supports gz/bzip2) containing the sequence(s) to query.
            zvalue: Z-value parameter for the query.
            threshold: Threshold parameter for the query.
            monitor: Whether to monitor resource usage.
            is_compressed: Whether the index is compressed.

        Returns:
            Path to the output directory with query results.

        Raises:
            NotADirectoryError: If index path doesn't exist.
            FileNotFoundError: If index.json or query_file not found.
            IsADirectoryError: If output_dir already exists.
        """

        registry = None

        input_registry = Toolbox.get_canonical_path(input_registry)
        output_dir = Toolbox.get_canonical_path(output_dir)

        # Validate query file exists
        query_file = Toolbox.get_canonical_path(str(query_file))
        if not os.path.exists(query_file):
            raise FileNotFoundError(f"Query file not found: {query_file}")

        # Call existing query_index method
        # TODO:  Add   -b --batch-size   - Size of query batches (0≈nb_seq/nb_thread). {0}
        # add -s option
        Kmindex.query_index(
            names=names,
            index_path=input_registry,
            output_dir=output_dir,
            format=format,
            fastx=query_file,
            zvalue=zvalue,
            threshold=threshold,
            monitor=monitor,
            is_compressed=is_compressed,
        )

        return 
