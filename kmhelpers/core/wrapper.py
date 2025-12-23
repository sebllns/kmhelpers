"""
KmindexWrapper - High-level interface for kmindex build and query operations.
"""

import os
import yaml
import inspect
from typing import List, Optional, Union
from pathlib import Path

from .utils import Bin, Toolbox, Kmindex


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
        pass

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
        verbose: str = "info",
    ) -> tuple[str, str]:
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

        if not output_index_dir:
            raise ValueError("output_index_dir must be provided.")

        assert k >= 8 and k <= 255

        # Handle fof file creation if input_files provided
        input_fof_file = Toolbox.get_canonical_path(str(input_fof_file))
        if not os.path.exists(input_fof_file):
            raise FileNotFoundError(f"File-of-filenames not found: {input_fof_file}")

        output_registry_path = Toolbox.get_canonical_path(str(output_registry_path))

        # Set default register_as if not provided (required parameter)
        if register_as is None:
            register_as = os.path.splitext(os.path.basename(input_fof_file))[0]

        output_index_dir = Toolbox.get_canonical_path(
            os.path.join(
                os.path.dirname(output_registry_path), output_index_dir, register_as
            )
        )

        if os.path.exists(output_index_dir):
            raise FileExistsError(
                f"output_index_dir directory already exists: {output_index_dir}"
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

        print(f"Build index {register_as}")
        print(f"  - Parameters:")
        print(f"    - Input samples: {input_fof_file}")
        print(f"    - k: {k}")
        print(f"    - Bloom filter size: {bloom_size}")
        print(f"    - Partition count: {nb_partitions}")
        print(f"  - Parameters exported in: {output_log_dir}")
        print(f"  - Output data directory: {output_index_dir}")
        print(f"  - Registry: {output_registry_path}")
        print(f"  - Log dir: {output_log_dir}")

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

            with open(output_param_file, "w") as f:
                yaml.safe_dump(d, f)

        # Execute command
        result = Toolbox.monitor_cmd(cmd, print_trace=False, log_file=log_file)

        assert result, "Failed to build index"

        if output_log_dir:
            with open(
                os.path.join(output_log_dir, "kmindex_monitoring.yaml"), "w"
            ) as f:
                yaml.safe_dump(result, f)

        assert os.path.isdir(
            output_index_dir
        ), f"Could not find data directory {output_index_dir}"
        assert os.path.exists(
            os.path.join(output_registry_path, register_as)
        ), f"Could not find index in registry {output_registry_path}"

        return output_registry_path, register_as

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
        threads: int = 1,
    ) -> dict[str, str]:
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

        if not Kmindex.b_json_exists(index_path):
            raise FileNotFoundError(f"index.json not found in index path {index_path}")

        if os.path.isdir(output_dir):
            raise IsADirectoryError(
                f"Output directory {output_dir} already exists, please provide a non-existing directory"
            )

        cmd = [
            Bin.kmindex(),
            "query",
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

        result = Toolbox.monitor_cmd(cmd, print_trace=True)

        if not result:
            raise RuntimeError("Query failed.")

        if not os.path.isdir(output_dir):
            raise NotADirectoryError(f"Result directory not found: {output_dir}")

        return result

    def kmindex_version(self) -> Optional[str]:
        try:
            v = Toolbox.run_cmd([Bin.kmindex(), "--version",])
            return v[8:]
        except Exception as e:
            print(f"Could not get kmindex version: {e}")
            return None