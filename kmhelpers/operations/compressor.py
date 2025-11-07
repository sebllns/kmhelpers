from dataclasses import dataclass
import os
import sys
from pathlib import Path
from kmhelpers.core.index import KmtricksIndex, IndexCompressionState
from kmhelpers.core.utils import Toolbox, Kmindex, BlockCompressorZSTD
from enum import Enum


class PermutationFlag(Enum):
    PERMUTATION_ENABLED = 0
    PERMUTATION_DISABLED = 1


@dataclass
class CompressionParams:
    block_size: int = 8388608
    group_size: int = 0
    subsample_size: int = 20000
    threshold: int = 0
    enable_check: bool = False
    enable_overwrite: bool = False
    # use_hash: bool = True
    force_permutation: bool = False
    with_checks: bool = False
    with_size_comparison: bool = True


class Compressor:
    """
    Handles compression of kmtricks index matrices using ZSTD block compression.

    This class provides functionality to compress individual matrix files or entire
    kmtricks indexes with optional column permutation for improved compression. The
    permutation reorders columns (samples) to group similar patterns together, which
    improves compression ratios when combined with block-based ZSTD compression.

    Attributes:
        enable_metrics (bool): Whether to collect and save compression metrics during operations.
    """

    def __init__(self, enable_metrics: bool = True):
        """
        Initialize the Compressor.

        Args:
            enable_metrics: If True, compression metrics will be saved to JSON files
                           during compression operations. Defaults to True.
        """
        self.enable_metrics = enable_metrics

    def _write_csv_header(
        self, size_path: Path, include_unordered: bool
    ) -> None:
        """Write CSV header if file doesn't exist."""
        if not os.path.isfile(size_path):
            with open(size_path, "w") as f:
                if include_unordered:
                    f.write(
                        "partition,original_byte_length,ordered_byte_length,unordered_byte_length\n"
                    )
                else:
                    f.write(
                        "partition,original_byte_length,ordered_byte_length\n"
                    )

    def _write_size_comparison(
        self,
        size_path: Path,
        partition: int,
        original_size: int,
        ordered_size: int,
        unordered_size: int = 0,
    ) -> None:
        """Write size comparison data to CSV file."""
        with open(size_path, "a") as f:
            if unordered_size > 0:
                f.write(
                    f"{partition},{original_size},{ordered_size},{unordered_size}\n"
                )
            else:
                f.write(f"{partition},{original_size},{ordered_size}\n")

    def _compress_and_measure_unordered(
        self,
        params: CompressionParams,
        idx: KmtricksIndex,
        partition: int,
        permutation_path: Path,
        config_path: Path,
        json_path: str,
        unordered_path: str,
    ) -> int:
        """Compress without ordering and return unordered size."""
        self.compress_file(
            params,
            idx.get_matrix_path(partition, False),
            idx.nb_samples,
            str(permutation_path),
            unordered_path,
            str(config_path),
            json_path,
            PermutationFlag.PERMUTATION_DISABLED,
        )
        assert os.path.isfile(unordered_path), f"File not found: {unordered_path}"
        unordered_size = Toolbox.get_size(unordered_path)
        os.remove(unordered_path)
        return unordered_size

    def compress_file(
        self,
        params: CompressionParams,
        input_matrix_path: str,
        matrix_columns_count: int,
        permutation_path: str,
        output_compressed_path: str,
        config_path: str,
        output_metric_path: str = "",
        permutation_flag: PermutationFlag = PermutationFlag.PERMUTATION_ENABLED,
    ) -> None:
        """
        Compress a single matrix file using ZSTD block compression.

        This method compresses a binary matrix file, optionally applying column permutation
        to reorder samples for improved compression ratios. The permutation groups similar
        columns together, improving the effectiveness of ZSTD block compression.

        Args:
            params: Compression parameters including block size, group size, subsample size,
                   and threshold values.
            input_matrix_path: Path to the input uncompressed matrix file.
            matrix_columns_count: Number of columns (samples) in the matrix.
            permutation_path: Path to the permutation file for column reordering.
                             Can be empty if permutation is disabled or forced.
            output_compressed_path: Path where the compressed matrix will be saved.
            config_path: Path to the configuration file for compression settings.
            output_metric_path: Optional path to save compression metrics as JSON.
                               Empty string disables metrics output.
            permutation_flag: Flag to enable or disable column permutation application.
                             Defaults to PERMUTATION_ENABLED.

        Raises:
            FileNotFoundError: If the input matrix file does not exist.
            ValueError: If output_compressed_path, config_path are empty, or if
                       matrix_columns_count is not positive, or if permutation_path
                       is empty when permutation is enabled.

        Note:
            Compression is skipped if the output file already exists and
            params.enable_overwrite is False.
        """
        # Check input_matrix_path exists
        if not os.path.exists(input_matrix_path):
            raise FileNotFoundError(f"Input matrix file not found: {input_matrix_path}")

        if not output_compressed_path:
            raise ValueError("Output compressed path cannot be empty")

        if not config_path:
            raise ValueError("Config file path cannot be empty")

        if matrix_columns_count <= 0:
            raise ValueError("Matrix columns count must be greater than zero")

        do_compress = params.enable_overwrite or not os.path.isfile(
            output_compressed_path
        )

        disable_permutation = permutation_flag == PermutationFlag.PERMUTATION_DISABLED

        if params.force_permutation or disable_permutation:
            permutation_path = ""
        elif not permutation_path:
            raise ValueError("Permutation path cannot be empty")

        if not self.enable_metrics:
            output_metric_path = ""

        if do_compress:
            print(f"Compress {input_matrix_path}...")

            BlockCompressorZSTD.compress_matrix(
                input_matrix_path,
                matrix_columns_count,
                permutation_path,
                output_compressed_path,
                config_path,
                output_metric_path,
                params.block_size,
                params.group_size,
                params.subsample_size,
                params.threshold,
                disable_permutation,
            )

            assert os.path.isfile(output_compressed_path), ""
            assert os.path.isfile(output_compressed_path + ".ef"), ""

    def compress_partition(
        self,
        params: CompressionParams,
        idx: KmtricksIndex,
        partition: int,
        output_dir: str,
        permutation_path: Path,
        config_path: Path,
        metrics_path: Path,
        size_path: Path,
        unordered_path: str,
        permutation_flag: PermutationFlag = PermutationFlag.PERMUTATION_ENABLED,
        compare_unordered: bool = False,
        is_reference: bool = False,
    ) -> None:
        """
        Compress a single partition of a kmtricks index.

        This method handles the compression of one partition, including optional size
        comparison and unordered compression for benchmarking.

        Args:
            params: Compression parameters.
            idx: The KmtricksIndex object containing the matrix.
            partition: Partition ID to compress.
            output_dir: Directory where compressed data will be saved.
            permutation_path: Path to the permutation file.
            config_path: Path to the configuration file.
            metrics_path: Path to the metrics directory.
            size_path: Path to the size comparison CSV file.
            unordered_path: Temporary path for unordered compression.
            permutation_flag: Controls whether to apply permutation.
            compare_unordered: If True, also compress without permutation for comparison.
            is_reference: If True, this is the reference partition that generates permutation.

        Raises:
            Exception: If compression fails.
        """
        compressed_path = Kmindex.get_matrix_path(
            index_path=output_dir, partition=partition, is_compressed=True
        )

        # No reference, when no permutation
        if permutation_flag == PermutationFlag.PERMUTATION_DISABLED:
            is_reference = False

        if is_reference:
            json_path = str(metrics_path / "ref.json") if self.enable_metrics else ""
        else:
            json_path = (
                str(metrics_path / f"bitmatrixshuffle_{partition}.json")
                if self.enable_metrics
                else ""
            )


        self.compress_file(
            params,
            idx.get_matrix_path(partition, False),
            idx.nb_samples,
            str(permutation_path),
            compressed_path,
            str(config_path),
            json_path,
            permutation_flag,
        )

        # Handle size comparison
        if params.with_size_comparison:
            original_size = idx.get_matrix_byte_size(partition, False)
            ordered_size = idx.get_matrix_byte_size(partition, True)
            should_compare_unordered = (
                compare_unordered
                and permutation_flag != PermutationFlag.PERMUTATION_DISABLED
            )

            # Write header only for reference partition
            if is_reference:
                self._write_csv_header(size_path, should_compare_unordered)

            if should_compare_unordered:
                unordered_size = self._compress_and_measure_unordered(
                    params,
                    idx,
                    partition,
                    permutation_path,
                    config_path,
                    json_path,
                    unordered_path,
                )
                self._write_size_comparison(
                    size_path, partition, original_size, ordered_size, unordered_size
                )
            else:
                self._write_size_comparison(
                    size_path, partition, original_size, ordered_size
                )

    def compress_full_index(
        self, params: CompressionParams, idx: KmtricksIndex, output_dir: str = ""
    ) -> None:
        """
        Compress all partitions of a kmtricks index.

        This is a convenience method that compresses all partitions in the index,
        using the first partition as the reference matrix for computing the
        column permutation.

        Args:
            params: Compression parameters to use for all partitions.
            idx: The KmtricksIndex object containing the matrices to compress.
            output_dir: Directory where compressed matrices will be saved.
                       If empty, uses the index's directory. Defaults to empty string.

        Note:
            This method delegates to compress_index_selection with all partitions
            included in the matrix list.
        """
        print(
            f"Compressing index {idx.index_id} with {idx.nb_partitions} partitions..."
        )
        self.compress_index_selection(
            params, idx, 1, list(range(idx.nb_partitions + 1)), output_dir
        )

    def compress_index_selection(
        self,
        params: CompressionParams,
        idx: KmtricksIndex,
        ref_matrix: int,
        matrix_list: list[int] = [],
        output_dir: str = "",
        permutation_flag: PermutationFlag = PermutationFlag.PERMUTATION_ENABLED,
        compare_unordered: bool = False,
    ) -> None:
        """
        Compress a selection of matrices from a kmtricks index.

        This method compresses a reference matrix and a list of additional matrices
        from a kmtricks index. The reference matrix is analyzed to compute an optimal
        column (sample) permutation using VP-tree clustering, which is then applied
        to all other matrices for improved compression.

        The method creates the following directory structure in output_dir:
        - matrices/: Contains compressed matrix files (.zst and .zst.ef)
        - permutation.bin: Column permutation file computed from reference matrix
        - config.cfg: Compression configuration file
        - metrics/ (optional): Contains compression metrics in JSON format
        - metrics/sizes.csv (optional): CSV file with size comparisons

        Args:
            params: Compression parameters including block size, group size, subsample size,
                   threshold, and flags for overwrite and size comparison.
            idx: The KmtricksIndex object containing the matrices to compress.
            ref_matrix: Partition ID of the reference matrix used to compute the column permutation.
                       This matrix is compressed first and its permutation is used for others.
            matrix_list: List of partition IDs to compress after the reference matrix.
                        Defaults to empty list.
            output_dir: Directory where compressed data will be saved. If empty, uses
                       the index's directory. Defaults to empty string.
            permutation_flag: Controls whether to apply permutation to non-reference matrices.
                             The reference matrix always uses permutation to compute it.
                             Defaults to PERMUTATION_ENABLED.
            compare_unordered: If True and permutation is enabled, also compresses matrices
                              without permutation to compare sizes. Results are saved to
                              sizes.csv. Defaults to False.

        Raises:
            Exception: If the reference matrix cannot be compressed or column permutation cannot
                      be computed. Individual matrix compression failures are caught and
                      logged but do not stop the overall process.

        Note:
            - The reference matrix is always compressed with permutation enabled to generate
              the column permutation file, regardless of the permutation_flag parameter.
            - The computed permutation reorders columns (samples) to group similar patterns.
            - If params.with_size_comparison is True, a CSV file with compression statistics
              is created in the metrics directory.
            - If output_dir equals idx.dir_path, the index compression state is updated to BOTH.
        """

        if not output_dir:
            output_dir = idx.dir_path

        output_dir = Toolbox.get_canonical_path(output_dir)

        metrics_path = Path(output_dir, "metrics")
        matrices_path = Path(output_dir, "matrices")
        permutation_path = Path(output_dir, "permutation.bin")
        config_path = Path(output_dir, "config.cfg")
        size_path = metrics_path / "sizes.csv"

        Path(output_dir).mkdir(parents=True, exist_ok=True)
        matrices_path.mkdir(parents=True, exist_ok=True)

        if self.enable_metrics:
            metrics_path.mkdir(parents=False, exist_ok=True)

        unordered_path = str(matrices_path / "~zstd_tmp")

        # Reference matrix
        try:
            self.compress_partition(
                params,
                idx,
                ref_matrix,
                output_dir,
                permutation_path,
                config_path,
                metrics_path,
                size_path,
                unordered_path,
                permutation_flag,
                compare_unordered,
                is_reference=True,
            )

            assert os.path.isfile(
                permutation_path
            ), f"Permutation file {permutation_path} not found"

        except Exception as error:
            print(
                f"FATAL: Could not compute permutation or compress reference matrix {ref_matrix}",
                file=sys.stderr,
            )
            print(error, file=sys.stderr)
            raise

        # Other matrices
        for i in matrix_list:
            try:
                self.compress_partition(
                    params,
                    idx,
                    i,
                    output_dir,
                    permutation_path,
                    config_path,
                    metrics_path,
                    size_path,
                    unordered_path,
                    permutation_flag,
                    compare_unordered,
                    is_reference=False,
                )
            except Exception as error:
                print(f"ERROR: Could not compress matrix {i}", file=sys.stderr)
                print(error, file=sys.stderr)

        if output_dir == idx.dir_path:
            idx.compress_state = IndexCompressionState.BOTH
