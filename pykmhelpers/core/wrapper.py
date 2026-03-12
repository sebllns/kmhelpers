"""
KmindexWrapper - High-level interface for kmindex build and query operations.
"""

import logging
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import psutil
import yaml

from .utils import Bin, Kmindex, Toolbox

logger = logging.getLogger(__name__)


class Wrapper:
    def __init__(
        self,
        dry_run: bool = False,
    ) -> None:
        self.dry_run = dry_run

    def _run_cmd(
        self,
        cmd: List[Any],
        print_trace: Optional[bool] = None,
        log_file: Optional[str] = None,
        log_errors_only: Optional[bool] = None,
    ) -> subprocess.CompletedProcess[str]:
        """
        Run a command using subprocess and capture its output.

        Args:
            cmd: Command and arguments as a list (converted to List[str])
            print_trace: Whether to print command output (default: computed from logger level)
            log_file: Optional path to write stdout/stderr to
            log_errors_only: Whether to log only errors (default: computed from logger level)

        Returns:
            CompletedProcess with stdout and stderr

        Raises:
            subprocess.SubprocessError: If command returns non-zero exit code
        """
        # Compute print_trace from logger level if not explicitly provided
        if print_trace is None:
            print_trace = logger.isEnabledFor(logging.DEBUG)

        if log_errors_only is None:
            log_errors_only = logger.getEffectiveLevel() >= logging.WARNING

        if self.dry_run:
            result = subprocess.CompletedProcess[str]([str(arg) for arg in cmd], 0)
        else:
            # Run command
            result = subprocess.run(
                [str(arg) for arg in cmd], capture_output=True, text=True
            )

        # Build output content
        output_lines = [
            f"Command: {' '.join(str(arg) for arg in cmd)}",
        ]

        if not log_errors_only and result.stdout.strip():
            output_lines.extend(["\n--- STDOUT ---", result.stdout])

        if result.stderr.strip():
            output_lines.extend(["\n--- STDERR ---", result.stderr])

        output_content = "\n".join(output_lines) if log_file or print_trace else ""

        # Print to console if print_trace is enabled
        if print_trace:
            logger.info(output_content)

        # Write to log file if specified
        if log_file:
            logger.debug(f"Logging output to: {log_file}")
            with open(log_file, "w") as f:
                f.write(output_content)

        if result.returncode != 0:
            raise subprocess.SubprocessError(
                f"Command {cmd[0]} returned code {result.returncode}\nLog: {result.stderr}"
            )
        return result

    def _monitor_cmd(
        self,
        cmd: List[Any],
        print_trace: Optional[bool] = None,
        log_file: Optional[str] = None,
        log_errors_only: Optional[bool] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Run a command and monitor its resource usage.
        Args:
            cmd: Command and arguments as a list
            print_trace: Whether to print trace output. If None, computed from logger level (True if DEBUG).
            log_file: Optional path to write stdout/stderr to
        Returns:
            Tuple of (stdout, resource_stats) where resource_stats contains:
                - start_time: Command start timestamp
                - execution_time_s: Execution time in seconds
                - max_cpu_percent: Maximum CPU usage percentage
                - max_memory_mb: Maximum memory usage in MB
                - return_code: Command exit code
                - error: Error message if command failed
            Returns None if process cannot be started
        """
        _cmd = [str(arg) for arg in cmd]

        if self.dry_run:
            return {"command": " ".join(_cmd)}

        # Compute print_trace from logger level if not explicitly provided
        if print_trace is None:
            print_trace = logger.isEnabledFor(logging.DEBUG)

        if log_errors_only is None:
            log_errors_only = logger.getEffectiveLevel() >= logging.WARNING

        max_cpu = 0.0
        max_memory = 0.0
        monitoring = True
        monitor_lock = threading.Lock()

        def monitor_resources(process):
            nonlocal max_cpu, max_memory, monitoring
            try:
                psutil_process = psutil.Process(process.pid)
                psutil_process.cpu_percent(interval=0.1)

                while monitoring and process.poll() is None:
                    try:
                        processes = [psutil_process] + psutil_process.children(
                            recursive=True
                        )

                        cpu_percent = sum(p.cpu_percent() for p in processes)
                        memory_bytes = sum(p.memory_info().rss for p in processes)
                        memory_mb = memory_bytes / 1024 / 1024

                        with monitor_lock:
                            max_cpu = max(max_cpu, cpu_percent)
                            max_memory = max(max_memory, memory_mb)

                        time.sleep(0.1)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        break
            except Exception as e:
                logger.error(f"Resource monitoring error: {e}")

        try:
            start_time = time.time()
            result = subprocess.Popen(
                _cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )

            monitor_thread = threading.Thread(target=monitor_resources, args=(result,))
            monitor_thread.daemon = True
            monitor_thread.start()
            time.sleep(0.01)

            stdout, stderr = result.communicate()
            end_time = time.time()
            monitoring = False
            monitor_thread.join(timeout=1)

            execution_time = end_time - start_time

            with monitor_lock:
                output = {
                    "command": " ".join(_cmd),
                    "start_time": start_time,
                    "execution_time_s": round(execution_time, 4),
                    "max_cpu_percent": round(max_cpu, 4),
                    "max_memory_mb": round(max_memory, 4),
                    "return_code": result.returncode,
                }
                if not log_errors_only:
                    output["stdout"] = stdout
                output["stderr"] = stderr

            # Build output content
            output_lines = [
                f"Command: {output['command']}",
                f"Execution time: {output['execution_time_s']}ms",
                f"Max CPU: {output['max_cpu_percent']}%",
                f"Max Memory: {output['max_memory_mb']} MB",
                f"Return code: {output['return_code']}",
            ]

            if not log_errors_only:
                output_lines.extend(["\n--- STDOUT ---", stdout])

            if stderr.strip():
                output_lines.extend(["\n--- STDERR ---", stderr])

            output_content = "\n".join(output_lines) if log_file or print_trace else ""

            # Print to console if print_trace is enabled
            if print_trace:
                logger.info(output_content)

            # Write to log file if specified
            if log_file:
                logger.debug(f"Logging output to: {log_file}")
                with open(log_file, "w") as f:
                    f.write(output_content)

            return output

        except Exception as e:
            logger.error(f"Failed to start process: {e}")
            return None


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
        super().__init__(dry_run=dry_run)

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
    ) -> Dict[str, str]:
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

        if not Kmindex.b_json_exists(input_registry):
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
            Bin.kmindex(),
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

        if not Kmindex.b_json_exists(input_registry):
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
            Bin.kmindex(),
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
                    Bin.kmindex(),
                    "--version",
                ],
                log_errors_only=True,
            )
            return v.stderr[8:]
        except Exception as e:
            logger.warning(f"Could not get kmindex version: {e}")
            return None
