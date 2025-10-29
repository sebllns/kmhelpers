from dataclasses import dataclass
import os
from pathlib import Path
from kmhelpers.core.index import Index, IndexCompressionState
from kmhelpers.core.utils import BlockCompressorZSTD


@dataclass
class CompressionParams:
    block_size: int = 8388608
    group_size: int = 0
    subsample_size: int = 20000
    threshold: float = 0.0
    enable_check: bool = False
    enable_overwrite: bool = False
    # use_hash: bool = True
    force_permutation: bool = False


class Compressor:
    def __init__(self, enable_metrics: bool = True):
        self.enable_metrics = enable_metrics

    def compress_file(
        self,
        params: CompressionParams,
        input_matrix_path: str,
        matrix_columns_count: int,
        permutation_path: str,
        output_compressed_path: str,
        config_path: str,
        output_metric_path: str = "",
    ):
        # Check input_matrix_path exists
        if not os.path.exists(input_matrix_path):
            raise FileNotFoundError(f"Input matrix file not found: {input_matrix_path}")

        if not permutation_path:
            raise ValueError("Permutation path cannot be empty")

        if not output_compressed_path:
            raise ValueError("Output compressed path cannot be empty")

        if not config_path:
            raise ValueError("Config file path cannot be empty")

        if matrix_columns_count <= 0:
            raise ValueError("Matrix columns count must be greater than zero")

        s = ""
        if os.path.isfile(permutation_path):
            s = "f"
        else:
            s = "t"

        do_compress = params.enable_overwrite or not os.path.isfile(
            output_compressed_path
        )

        if do_compress:
            print(f"Compress {input_matrix_path}...")
            BlockCompressorZSTD.compress_matrix(
                f"-i {input_matrix_path}",
                "--header 49",
                f"-c {matrix_columns_count}",
                f"-g {params.group_size}",
                f"-s {params.subsample_size}",
                f"-b {params.block_size}",
                f"--threshold {params.threshold}",
                f"--config-path {config_path}",
                f"-{s} {permutation_path}" if not params.force_permutation else "",
                f"-z {output_compressed_path}" if output_compressed_path else "",
                (
                    f"-j {output_metric_path}"
                    if (self.enable_metrics and output_metric_path)
                    else ""
                ),
            )

    def compress_full_index(self, params: CompressionParams, idx: Index):
        print(
            f"Compressing index {idx.index_id} with {idx.nb_partitions} partitions..."
        )
        self.compress_index_selection(
            params, idx, 1, list(range(0, idx.nb_partitions + 1))
        )

    def compress_index_selection(
        self,
        params: CompressionParams,
        idx: Index,
        ref_matrix: int,
        matrix_list: list[int] = [],
    ):
        # Reference matrix
        if self.enable_metrics:
            Path(idx.metrics_dir_path).mkdir(parents=False, exist_ok=True)

            compressed_path = idx.get_matrix_path(
                partition=ref_matrix, is_compressed=False
            )
            self.compress_file(
                params,
                compressed_path,
                idx.nb_samples,
                idx.permutation_path,
                idx.get_matrix_path(ref_matrix, True),
                idx.get_path_inside_index("config.cfg"),
                (
                    str(Path(idx.metrics_dir_path) / "ref.json")
                    if self.enable_metrics
                    else ""
                ),
            )

        # Other matrices
        for i in matrix_list:
            compressed_path = idx.get_matrix_path(partition=i, is_compressed=False)
            self.compress_file(
                params,
                compressed_path,
                idx.nb_samples,
                idx.permutation_path,
                idx.get_matrix_path(i, True),
                idx.get_path_inside_index("config.cfg"),
                (
                    str(Path(idx.metrics_dir_path) / f"{compressed_path}.json")
                    if self.enable_metrics
                    else ""
                ),
            )

        idx.compress_state = IndexCompressionState.BOTH
