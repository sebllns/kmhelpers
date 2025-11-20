"""
KmindexWrapper - High-level interface for kmindex build and query operations.
"""

import os
import subprocess
from typing import List, Optional, Union
from pathlib import Path

from .utils import Bin, Toolbox, Kmindex
from .index import KmtricksIndex
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
        self.fof_manager = FofManager()

    def create_fof_file(
        self,
        input_files: List[Union[str, Path]],
        fof_path: Union[str, Path],
        use_absolute_paths: bool = True,
    ) -> str:
        """
        Create a file-of-files (fof) from a list of input files.

        The fof format is: "name: path" where name is the sample identifier
        and path is the file path.

        This method delegates to FofManager for consistent fof operations.

        Args:
            input_files: List of input file paths.
            fof_path: Path where the fof file should be created.
            use_absolute_paths: If True, convert all paths to absolute paths.

        Returns:
            Absolute path to the created fof file.

        Raises:
            FileNotFoundError: If any input file doesn't exist.
        """
        return self.fof_manager.create_fof_file(
            input_files=input_files,
            fof_path=fof_path,
            use_absolute_paths=use_absolute_paths,
            validate_files=True,
        )

    def build(
        self,
        index_path: Union[str, Path],
        input_files: Optional[List[Union[str, Path]]] = None,
        fof_file: Optional[Union[str, Path]] = None,
        kmer_size: int = 31,
        minim_size: int = 10,
        bloom_size: Optional[int] = None,
        nb_cell: Optional[int] = None,
        bitw: int = 2,
        hard_min: int = 2,
        nb_partitions: int = 0,
        threads: int = 1,
        compress_intermediate: bool = False,
        register_as: Optional[str] = None,
        run_dir: Optional[Union[str, Path]] = None,
        from_index: Optional[str] = None,
        km_path: Optional[Union[str, Path]] = None,
        verbose: str = "info",
        auto_cleanup_fof: bool = True,
    ) -> KmtricksIndex:
        """
        Build a kmindex index.

        Args:
            index_path: Output index path.
            input_files: List of input FASTA/FASTQ files (will create temporary fof).
            fof_file: Path to file-of-filenames. Either this or input_files required.
            kmer_size: K-mer size (8-255).
            minim_size: Minimizer size (4-15).
            bloom_size: Bloom filter size for presence/absence indexing.
            nb_cell: Number of cells for abundance indexing (mutually exclusive with bloom_size).
            bitw: Bits per cell for abundance indexing (creates 2^bitw classes).
            hard_min: Minimum k-mer abundance threshold.
            nb_partitions: Number of partitions (0=auto).
            threads: Number of threads.
            compress_intermediate: Whether to compress intermediate files (--cpr flag).
            register_as: Register index with this name.
            run_dir: kmtricks runtime directory.
            from_index: Use parameters from a pre-registered index.
            km_path: Path to kmtricks binary (if not in $PATH).
            verbose: Verbosity level (debug|info|warning|error).
            auto_cleanup_fof: If True and input_files provided, delete temporary fof after build.

        Returns:
            KmtricksIndex object representing the built index.

        Raises:
            ValueError: If neither input_files nor fof_file provided, or if both bloom_size
                       and nb_cell are specified.
            FileNotFoundError: If fof_file doesn't exist or input files not found.
            subprocess.CalledProcessError: If kmindex build command fails.
        """
        # Validate inputs
        if input_files is None and fof_file is None:
            raise ValueError("Either input_files or fof_file must be provided")

        if bloom_size is not None and nb_cell is not None:
            raise ValueError(
                "bloom_size and nb_cell are mutually exclusive. "
                "Use bloom_size for presence/absence indexing or nb_cell for abundance indexing."
            )

        # Handle fof file creation if input_files provided
        temp_fof = None
        if input_files is not None:
            temp_fof = os.path.join(os.path.dirname(str(index_path)), ".tmp_fof.txt")
            fof_file = self.create_fof_file(input_files, temp_fof)
        else:
            fof_file = Toolbox.get_canonical_path(str(fof_file))
            if not os.path.exists(fof_file):
                raise FileNotFoundError(f"File-of-filenames not found: {fof_file}")

        index_path = Toolbox.get_canonical_path(str(index_path))

        # Build command
        cmd = [
            Bin.kmindex(),
            "build",
            "--index",
            index_path,
            "--fof",
            fof_file,
            "--kmer-size",
            str(kmer_size),
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

        if register_as is not None:
            cmd.extend(["--register-as", register_as])

        if run_dir is not None:
            cmd.extend(["--run-dir", str(run_dir)])

        if from_index is not None:
            cmd.extend(["--from", from_index])

        if km_path is not None:
            cmd.extend(["--km-path", str(km_path)])

        # Execute command
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            print(result.stdout)
            if result.stderr:
                print(result.stderr)
        except subprocess.CalledProcessError as e:
            print(f"Error building index: {e.stderr}")
            raise
        finally:
            # Cleanup temporary fof file if created
            if temp_fof is not None and auto_cleanup_fof and os.path.exists(temp_fof):
                os.remove(temp_fof)

        # Return KmtricksIndex object
        # For a newly built index, the index is at index_path and we need to extract
        # the parent directory and index name
        parent_dir = os.path.dirname(index_path)
        index_name = os.path.basename(index_path)

        # If parent_dir is empty (relative path), use current directory
        if not parent_dir:
            parent_dir = os.getcwd()

        return KmtricksIndex(parent_dir, index_name)

    def query(
        self,
        index: Union[str, Path, KmtricksIndex],
        query_file: Union[str, Path],
        output_dir: Union[str, Path],
        names: Optional[List[str]] = None,
        format: str = "json",
        fastx: bool = False,
        zvalue: int = 0,
        threshold: float = 0.0,
        monitor: bool = False,
        is_compressed: bool = False,
    ) -> str:
        """
        Query a kmindex index.

        This method wraps the existing Kmindex.query_index() functionality.

        Args:
            index: Path to index directory or KmtricksIndex object.
            query_file: Path to query FASTA/FASTQ file.
            output_dir: Path to output directory (must not exist).
            names: List of sample names to query (if None, queries all).
            format: Output format (e.g., "json").
            fastx: Whether to use FASTX format.
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
        # Handle KmtricksIndex object
        if isinstance(index, KmtricksIndex):
            index_path = index.dir_path
        else:
            index_path = str(index)

        # Validate query file exists
        query_file = Toolbox.get_canonical_path(str(query_file))
        if not os.path.exists(query_file):
            raise FileNotFoundError(f"Query file not found: {query_file}")

        # If no names provided, get all sample names from index
        if names is None:
            if isinstance(index, KmtricksIndex):
                idx = index
            else:
                parent_dir = os.path.dirname(index_path)
                index_name = os.path.basename(index_path)
                if not parent_dir:
                    parent_dir = os.getcwd()
                idx = KmtricksIndex(parent_dir, index_name)

            names = idx.samples

        # Call existing query_index method
        Kmindex.query_index(
            names=names,
            index_path=index_path,
            output_dir=str(output_dir),
            format=format,
            fastx=fastx,
            zvalue=zvalue,
            threshold=threshold,
            monitor=monitor,
            is_compressed=is_compressed,
        )

        return Toolbox.get_canonical_path(str(output_dir))
