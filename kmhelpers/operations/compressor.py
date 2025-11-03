from dataclasses import dataclass
import os
from pathlib import Path
from kmhelpers.core.index import KmtricksIndex, IndexCompressionState
from kmhelpers.core.utils import Kmindex, BlockCompressorZSTD


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
            args = [
                "-i",
                input_matrix_path,
                "--header",
                "49",
                "-c",
                str(matrix_columns_count),
                "-g",
                str(params.group_size),
                "-s",
                str(params.subsample_size),
                "-b",
                str(params.block_size),
            ]

            if not params.force_permutation:
                args.extend([f"-{s}", permutation_path])

            if output_compressed_path:
                args.extend(["-z", output_compressed_path])

            if self.enable_metrics and output_metric_path:
                args.extend(["-j", output_metric_path])

            if config_path:
                args.extend(["--config-path", config_path])

            if params.threshold > 0:
                args.extend(["--threshold", str(params.threshold)])

            return BlockCompressorZSTD.compress_matrix(*args)

    def compress_full_index(
        self, params: CompressionParams, idx: KmtricksIndex, output_dir: str = ""
    ):
        print(
            f"Compressing index {idx.index_id} with {idx.nb_partitions} partitions..."
        )
        self.compress_index_selection(
            params, idx, 1, list(range(0, idx.nb_partitions + 1)), output_dir
        )

    def compress_index_selection(
        self,
        params: CompressionParams,
        idx: KmtricksIndex,
        ref_matrix: int,
        matrix_list: list[int] = [],
        output_dir: str = "",
    ):
        metrics_path = Path(idx.metrics_dir_path)

        if output_dir:
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            Path(output_dir, "metrics").mkdir(parents=True, exist_ok=True)
            Path(output_dir, "matrices").mkdir(parents=True, exist_ok=True)
            metrics_path = Path(output_dir, "metrics")

        # Reference matrix
        if self.enable_metrics:
            metrics_path.mkdir(parents=False, exist_ok=True)

        compressed_path = (
            Kmindex.get_matrix_path(
                index_path=output_dir, partition=ref_matrix, is_compressed=True
            )
            if output_dir
            else idx.get_matrix_path(partition=ref_matrix, is_compressed=True)
        )
        self.compress_file(
            params,
            idx.get_matrix_path(ref_matrix, False),
            idx.nb_samples,
            idx.permutation_path,
            compressed_path,
            idx.get_path_inside_index("config.cfg"),
            (str(metrics_path / "ref.json") if self.enable_metrics else ""),
        )

        # Other matrices
        for i in matrix_list:
            compressed_path = (
                Kmindex.get_matrix_path(
                    index_path=output_dir, partition=i, is_compressed=True
                )
                if output_dir
                else idx.get_matrix_path(partition=i, is_compressed=True)
            )
            self.compress_file(
                params,
                idx.get_matrix_path(i, True),
                idx.nb_samples,
                idx.permutation_path,
                compressed_path,
                idx.get_path_inside_index("config.cfg"),
                (
                    str(metrics_path / f"{compressed_path}.json")
                    if self.enable_metrics
                    else ""
                ),
            )

        idx.compress_state = IndexCompressionState.BOTH
