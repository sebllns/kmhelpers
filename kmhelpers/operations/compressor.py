from dataclasses import dataclass
import os

from kmhelpers.core.index import Index
from kmhelpers.core.utils import BlockCompressorZSTD

@dataclass
class CompressionParams:
    block_size: int = 8388608
    group_size: int = 0
    subsample_size: int = 20000
    threshold: float = 0.0
    enable_check: bool = False
    enable_overwrite: bool = False


class Compressor:
    def __init__(self, enable_metrics: bool = True):
        self.enable_metrics = enable_metrics

    def compute_permutation(
        self,
        params: CompressionParams,
        input_matrix_path: str,
        matrix_columns_count: int,
        output_permutation_path: str,
        output_compressed_path: str = "", 
        output_metric_path: str = ""
    ):
        # Check input_matrix_path exists
        if not os.path.exists(input_matrix_path):
            raise FileNotFoundError(f"Input matrix file not found: {input_matrix_path}")
        
        # Check output_permutation_path is not empty
        if not output_permutation_path:
            raise ValueError("Output permutation path cannot be empty")
        
        if(params.enable_overwrite or not os.path.isfile(output_permutation_path)):
            print(f"Compute permutation from {input_matrix_path}...")
            BlockCompressorZSTD.compress_matrix(
                f"-i {input_matrix_path}",
                "--header 49",
                f"-c {matrix_columns_count}",
                f"-g {params.group_size}",
                f"-s {params.subsample_size}",
                f"-b {params.block_size}",
                f"--threshold {params.threshold}",
                f"-t {output_permutation_path}",
                f"-z {output_compressed_path}" if output_compressed_path else "",      
                f"-j {output_metric_path}" if (self.enable_metrics and output_metric_path) else "",   
            )

    def compress_file(self, params: CompressionParams, input_matrix_path: str, ):
        print("compress")

    def compress_index(
        self, params: CompressionParams, idx: Index, matrix_range: range = range(0, 0)
    ):
        print(f"Compressing index {idx.index_id} with {idx.nb_partitions} partitions...")
        if matrix_range.count == 0:
            matrix_range = range(0, idx.nb_partitions + 1)

        print(f"Processing partitions: {matrix_range}")
        for i in matrix_range:
            self.compress_file(
                params, idx.get_matrix_path(partition=i, is_compressed=False)
            )
