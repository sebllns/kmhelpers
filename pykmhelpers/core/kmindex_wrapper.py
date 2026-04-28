"""
KmindexWrapper - High-level interface for kmindex build and query operations.
"""

import logging
import os
from pathlib import Path
from typing import List, Optional, Union

import yaml

from pykmhelpers.core.system import maximize_nofile
from pykmhelpers.core.utils import Toolbox
from pykmhelpers.core.wrapper import Wrapper

logger = logging.getLogger(__name__)


class KmindexWrapper(Wrapper):
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

    def __init__(self, dry_run: bool = False):
        """Initialize the KmindexWrapper."""
        super().__init__(main_cmd="kmindex", dry_run=dry_run)

    def _get_verbose_level(self) -> str:
        """Convert logger level to kmindex verbose level string."""
        level = logger.getEffectiveLevel()
        if level <= logging.DEBUG:
            return "debug"
        elif level <= logging.INFO:
            return "info"
        elif level <= logging.WARNING:
            return "warning"
        else:
            return "error"

    def build(
        self,
        input_fof_file: Union[str, Path],
        output_registry_path: Union[str, Path] = "index",
        output_index_dir: Union[str, Path] = ".subindexes",
        output_log_dir: Optional[Union[str, Path]] = None,
        output_param_file: Optional[Union[str, Path]] = None,
        k: int = 25,
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
        inplace: bool = False,
    ) -> dict:
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

        Returns:
            None. Builds the index and outputs results to specified directories.

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

        if not input_fof_file:
            raise ValueError("Input sample file (FOF) must be provided.")

        if not output_index_dir and not inplace:
            raise ValueError("output_index_dir must be provided.")

        if not (8 <= k <= 255):
            raise ValueError(f"K-mer size must be between 8 and 255, got {k}")

        # Handle fof file creation if input_files provided
        input_fof_file = Toolbox.get_canonical_path(str(input_fof_file))
        if not os.path.exists(input_fof_file):
            raise FileNotFoundError(f"File-of-filenames not found: {input_fof_file}")

        output_registry_path = Toolbox.get_canonical_path(str(output_registry_path))

        # Set default register_as if not provided (required parameter)
        if register_as is None:
            register_as = os.path.splitext(os.path.basename(input_fof_file))[0]

        if inplace:
            output_index_dir = "@inplace"
        else:
            output_index_dir = Toolbox.get_canonical_path(
                os.path.join(
                    os.path.dirname(output_registry_path), output_index_dir, register_as
                )
            )

            if not self.dry_run and os.path.exists(output_index_dir):
                raise FileExistsError(
                    f"output_index_dir directory already exists: {output_index_dir}"
                )

            os.makedirs(os.path.dirname(output_index_dir), exist_ok=True)

        # Build command
        cmd = [
            self.main_cmd,
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
            self._get_verbose_level(),
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

        logger.debug(f"Build index {register_as}")
        logger.debug(f"  - Parameters:")
        logger.debug(f"    - Input samples: {input_fof_file}")
        logger.debug(f"    - k: {k}")
        logger.debug(f"    - Bloom filter size: {bloom_size}")
        logger.debug(f"    - Partition count: {nb_partitions}")
        if from_index:
            logger.debug(f"    - From: {from_index}")
        if output_param_file:
            logger.debug(f"  - Parameters exported in: {output_param_file}")
        logger.debug(f"  - Output data directory: {output_index_dir}")
        logger.debug(f"  - Registry: {output_registry_path}")
        logger.debug(f"  - Log dir: {output_log_dir}")

        # Set default log dir if not provided
        log_file = None
        if output_log_dir:
            output_log_dir = os.path.join(
                os.path.dirname(output_registry_path), output_log_dir
            )
            os.makedirs(output_log_dir, exist_ok=True)
            log_file = os.path.join(output_log_dir, "kmindex.log")

        if output_param_file:
            output_param_file = os.path.join(
                os.path.dirname(output_registry_path), output_param_file
            )

            d = {
                "input_fof_file": input_fof_file,
                "k": k,
                "nb_partitions": nb_partitions,
                "minim_size": minim_size,
                "hard_min": hard_min,
                "bitw": bitw,
            }

            if bloom_size:
                d["bloom_size"] = bloom_size

            if nb_cell:
                d["nb_cell"] = nb_cell

            if from_index:
                d["from"] = from_index

            with open(output_param_file, "w") as f:
                yaml.safe_dump(d, f)

        # Execute command
        maximize_nofile()
        result = self._monitor_cmd(cmd, log_file=log_file, log_errors_only=True)

        assert result, "Failed to build index"

        if output_log_dir:
            with open(
                os.path.join(output_log_dir, "kmindex_monitoring.yaml"), "w"
            ) as f:
                yaml.safe_dump(result, f)

        if not self.dry_run:
            assert os.path.isdir(
                output_index_dir
            ), f"Could not find data directory {output_index_dir}"
            assert os.path.exists(
                os.path.join(output_registry_path, register_as)
            ), f"Could not find index in registry {output_registry_path}"

        return result

    def query(
        self,
        input_registry: str,
        query_file: str,
        output_dir: str = "query_results",
        names: Optional[List[str]] = None,
        format: str = "json",
        zvalue: int = 0,
        threshold: float = 0.0,
        single_query: Optional[str] = None,
        aggregate: bool = False,
        fast: bool = True,
        is_compressed: bool = False,
        method: str = "seq",
        threads: int = 1,
    ) -> dict:
        """
        Query a kmindex index.

        This method wraps the existing Kmindex.query_index() functionality.

        Args:
            input_registry: Path to the registry directory (index.json parent directory).
            query_file: Path to query FASTA/FASTQ file (supports gz/bzip2 compression).
            output_dir: Path to output directory (must not exist).
            names: Sub-indexes to query. If None, query all sub-indexes.
            format: Output format (e.g., "json").
            zvalue: Z-value parameter for the query.
            threshold: Threshold parameter for the query.
            monitor: Whether to monitor resource usage.
            single_query: Query identifier. If provided, all sequences are considered as a unique query.
            aggregate: Whether to aggregate results from batches into one file.
            threads: Number of threads to use for the query.

        Returns:
            None. Query results are written to the output directory.

        Raises:
            FileNotFoundError: If query_file not found.
        """

        registry = None

        input_registry = Toolbox.get_canonical_path(input_registry)
        output_dir = Toolbox.get_canonical_path(output_dir)

        # Validate query file exists
        query_file = Toolbox.get_canonical_path(str(query_file))
        if not os.path.exists(query_file):
            raise FileNotFoundError(f"Query file not found: {query_file}")

        index_path = Toolbox.get_canonical_path(input_registry)
        output_dir = Toolbox.get_canonical_path(output_dir)

        if not os.path.isdir(index_path):
            raise NotADirectoryError(
                f"Index path {index_path} does not exist or is not a directory"
            )

        if not os.path.isfile(query_file):
            raise FileNotFoundError(f"Query file {query_file}  not found")

        if not self.b_json_exists(index_path):
            raise FileNotFoundError(f"index.json not found in index path {index_path}")

        if os.path.isdir(output_dir):
            raise IsADirectoryError(
                f"Output directory {output_dir} already exists, please provide a non-existing directory"
            )

        cmd = [
            self.main_cmd,
            "query2" if is_compressed or method == "sub" else "query",
            "--index",
            index_path,
            "--output",
            output_dir,
            "--format",
            format,
            "--fastx",
            query_file,
            "--zvalue",
            str(zvalue),
            "--threshold",
            str(threshold),
            "--threads",
            str(threads),
            "--verbose",
            self._get_verbose_level(),
        ]

        if single_query is not None:
            cmd.extend(["--single-query", single_query])

        if aggregate:
            cmd.append("--aggregate")

        if names:
            cmd.extend(
                [
                    "--names",
                    ",".join(names),
                ]
            )

        if fast:
            if is_compressed:
                logging.warning(
                    "Fast mode is not supported for compressed indexes; ignoring --fast flag."
                )
            else:
                cmd.append("--fast")

        result = self._monitor_cmd(cmd, log_errors_only=True)

        if not result:
            raise RuntimeError("Query failed.")

        if not os.path.isdir(output_dir):
            raise NotADirectoryError(f"Result directory not found: {output_dir}")

        return result

    def compress(
        self,
        input_registry: str,
        index_name: str,
        block_size: int = 8,
        sampling: int = 20000,
        column_per_block: int = 0,
        cpr_level: int = 3,
        threads: int = 14,
        reorder: bool = False,
        delete_uncompressed: bool = False,
        check_results: bool = False,
    ) -> dict:
        """
        Compress a kmindex index.

        This method wraps the kmindex compress command to compress an index with optional
        column reordering for better compression ratios.

        Args:
            input_registry: Path to the registry directory (index.json parent directory).
            index_name: Name of the index to compress.
            block_size: Size of uncompressed blocks in megabytes (default: 8).
            sampling: Number of rows to sample for reordering (default: 20000).
            column_per_block: Reorder columns by group of N (0=all columns together).
                             Must be a multiple of 8 (default: 0).
            cpr_level: Compression level in range [1-22] (default: 3).
            threads: Number of threads to use (default: 14).
            reorder: Whether to reorder columns before compressing (default: False).
            delete_uncompressed: Delete uncompressed index after successful compression (default: False).
            check_results: Check query results after compressing (default: False).

        Returns:
            Dictionary containing compression monitoring/execution results.

        Raises:
            NotADirectoryError: If input_registry doesn't exist or is not a directory.
            FileNotFoundError: If index.json not found in registry.
            ValueError: If column_per_block is not 0 or a multiple of 8.
            subprocess.CalledProcessError: If kmindex compress command fails.

        Example:
            >>> wrapper = KmindexWrapper()
            >>> result = wrapper.compress(
            ...     input_registry="/path/to/indices",
            ...     index_name="my_index",
            ...     reorder=True,
            ...     block_size=8,
            ...     threads=8
            ... )
        """

        # Validate inputs
        input_registry = Toolbox.get_canonical_path(input_registry)

        if not os.path.isdir(input_registry):
            raise NotADirectoryError(
                f"Registry path {input_registry} does not exist or is not a directory"
            )

        if not self.b_json_exists(input_registry):
            raise FileNotFoundError(
                f"index.json not found in registry {input_registry}"
            )

        # Validate column_per_block is 0 or multiple of 8
        if column_per_block != 0 and column_per_block % 8 != 0:
            raise ValueError(
                f"column_per_block must be 0 or a multiple of 8, got {column_per_block}"
            )

        # Validate compression level range
        assert cpr_level >= 1 and cpr_level <= 22, "cpr_level must be in range [1-22]"

        # Build command
        cmd = [
            self.main_cmd,
            "compress",
            "--global-index",
            input_registry,
            "--name",
            index_name,
            "--block-size",
            str(block_size),
            "--sampling",
            str(sampling),
            "--column-per-block",
            str(column_per_block),
            "--cpr-level",
            str(cpr_level),
            "--threads",
            str(threads),
            "--verbose",
            self._get_verbose_level(),
        ]

        # Add optional flags
        if reorder:
            cmd.append("--reorder")

        if delete_uncompressed:
            cmd.append("--delete")

        if check_results:
            cmd.append("--check")

        logger.debug(f"Compress index {index_name}")
        logger.debug(f"  - Registry: {input_registry}")
        logger.debug(f"  - Block size: {block_size} MB")
        logger.debug(f"  - Sampling: {sampling} rows")
        logger.debug(f"  - Compression level: {cpr_level}")
        logger.debug(f"  - Reorder: {reorder}")
        logger.debug(f"  - Threads: {threads}")

        # Execute command
        result = self._monitor_cmd(cmd, log_errors_only=True)

        if not result:
            raise RuntimeError("Compression failed.")

        return result

    def merge(
        self,
        input_registry: str,
        new_name: str,
        new_path: str,
        to_merge: List[str],
        rename: Optional[str] = None,
        delete_old: bool = False,
        threads: int = 14,
    ) -> dict:
        """
        Merge sub-indexes into a single index.

        This method wraps the kmindex merge command to combine multiple sub-indexes
        into a new index.

        Args:
            input_registry: Path to the global index registry directory (index.json parent).
            new_name: Name of the new merged index.
            new_path: Output path for the merged index.
            to_merge: List of sub-index names to merge.
            rename: Rename sample identifiers to resolve conflicts.
                   Can be specified in three ways:
                   - File-based: "f:id1.txt,id2.txt,id3.txt" (one identifier per line in each file)
                   - Format string: "s:id_{}" (where {} is replaced by integer in [0, nb_samples))
                   - Manual: None (edit kmtricks.fof files manually)
            delete_old: Whether to delete old sub-index files after successful merge.
            threads: Number of threads to use (default: 14).

        Returns:
            Dictionary containing merge monitoring/execution results.

        Raises:
            NotADirectoryError: If input_registry doesn't exist or is not a directory.
            FileNotFoundError: If index.json not found in registry.
            ValueError: If to_merge list is empty.
            subprocess.CalledProcessError: If kmindex merge command fails.

        Example:
            >>> wrapper = KmindexWrapper()
            >>> result = wrapper.merge(
            ...     input_registry="/path/to/indices",
            ...     new_name="merged_index",
            ...     new_path="/path/to/merged",
            ...     to_merge=["index1", "index2", "index3"],
            ...     rename="s:sample_{}"
            ... )
        """

        # Validate inputs
        input_registry = Toolbox.get_canonical_path(input_registry)

        if not os.path.isdir(input_registry):
            raise NotADirectoryError(
                f"Registry path {input_registry} does not exist or is not a directory"
            )

        if not self.b_json_exists(input_registry):
            raise FileNotFoundError(
                f"index.json not found in registry {input_registry}"
            )

        if not to_merge or len(to_merge) == 0:
            raise ValueError("to_merge list cannot be empty")

        if not new_name:
            raise ValueError("new_name must be provided")

        if not new_path:
            raise ValueError("new_path must be provided")

        new_path = Toolbox.get_canonical_path(new_path)

        # Build command
        cmd = [
            self.main_cmd,
            "merge",
            "--index",
            input_registry,
            "--new-name",
            new_name,
            "--new-path",
            new_path,
            "--to-merge",
            ",".join(to_merge),
            "--threads",
            str(threads),
            "--verbose",
            self._get_verbose_level(),
        ]

        # Add optional parameters
        if rename:
            cmd.extend(["--rename", rename])

        if delete_old:
            cmd.append("--delete-old")

        logger.debug(f"Merge indexes into {new_name}")
        logger.debug(f"  - Registry: {input_registry}")
        logger.debug(f"  - Sub-indexes to merge: {', '.join(to_merge)}")
        logger.debug(f"  - New index name: {new_name}")
        logger.debug(f"  - Output path: {new_path}")
        logger.debug(f"  - Rename: {rename if rename else 'None'}")
        logger.debug(f"  - Delete old: {delete_old}")
        logger.debug(f"  - Threads: {threads}")

        # Execute command
        result = self._monitor_cmd(cmd, log_errors_only=True)

        if not result:
            raise RuntimeError("Merge failed.")

        return result

    def kmindex_version(self) -> Optional[str]:
        try:
            v = self._run_cmd(
                [
                    self.main_cmd,
                    "--version",
                ],
                log_errors_only=True,
            )
            return v.stderr[9:].strip()
        except Exception as e:
            logger.warning(f"Could not get kmindex version: {e}")
            return None

    ####################################################
    def get_matrix_dir(self, index_path: str) -> str:
        """
        Get the path to the matrices directory within an index.

        Args:
            index_path: Path to the index directory

        Returns:
            Canonical path to the matrices directory
        """
        return Toolbox.get_canonical_path(os.path.join(index_path, "matrices"))

    ####################################################
    def get_matrix_path(
        self, index_path: str, partition: int, is_compressed: bool = False
    ) -> str:
        """
        Get the path to a specific matrix partition file.

        Args:
            index_path: Path to the index directory
            partition: Partition number
            is_compressed: Whether to get the compressed matrix path (default: False)

        Returns:
            Path to the matrix file (either matrix_N.cmbf or blocks_N for compressed)
        """
        return os.path.join(
            self.get_matrix_dir(index_path),
            f"blocks_{partition}" if is_compressed else f"matrix_{partition}.cmbf",
        )

        ####################################################

    @staticmethod
    def get_index_path(root: str, index: str) -> str:
        """
        Get the full path to an index directory.

        Args:
            root: Root directory containing indices
            index: Index ID or name

        Returns:
            Canonical path to the index directory
        """
        return Toolbox.get_canonical_path(os.path.join(root, index))

    ####################################################
    @staticmethod
    def get_path_inside_index(root: str, file: str) -> str:
        """
        Get the full path to a file within an index directory.

        Args:
            root: Index root directory
            file: Relative file path within the index

        Returns:
            Canonical path to the file
        """
        return Toolbox.get_canonical_path(os.path.join(root, file))

    ####################################################
    def get_options_path(self, root: str) -> str:
        """Get the path to options.txt file within an index directory."""
        return self.get_path_inside_index(root, "options.txt")

    ####################################################
    def get_json_path(self, root: str) -> str:
        """Get the path to index.json file within a directory."""
        return self.get_path_inside_index(root, "index.json")

    def b_json_exists(self, root: str) -> bool:
        """
        Check if index.json exists in the given directory.

        Args:
            root: Directory to check

        Returns:
            True if index.json exists
        """
        return os.path.isfile(self.get_json_path(root))
