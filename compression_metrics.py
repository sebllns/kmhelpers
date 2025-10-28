import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

from index import Index

@dataclass
class PermutationData:
    input_path: str = ""
    is_compressed: bool = False
    groupsize: int = 0
    nb_cols: int = 0
    nb_rows: int = 0
    subsample_size: int = 0
    computed_distances: int = 0
    max_computable_distances: int = 0
    pct_computed_distances: float = 0.0
    distance_avg_original: float = 0.0
    distance_avg_reorder: float = 0.0
    distance_stdev_original: float = 0.0
    distance_stdev_reorder: float = 0.0
    compressibility_factor: float = 1.0
    time_permutation_s: float = 0.0
    time_reorder_s: float = 0.0

    @classmethod
    def from_json(cls, data: dict) -> "PermutationData":
        return cls(
            input_path=data.get("0_input_path", ""),
            is_compressed=data.get("0_is_compressed", False),
            groupsize=data.get("1_groupsize", 0),
            nb_cols=data.get("1_nb_cols", 0),
            nb_rows=data.get("1_nb_rows", 0),
            subsample_size=data.get("1_subsample_size", 0),
            computed_distances=data.get("2a_computed_distances", 0),
            max_computable_distances=data.get("2a_max_computable_distances", 0),
            pct_computed_distances=data.get("2a_pct_computed_distances(%)", 0.0),
            distance_avg_original=data.get(
                "2b_consecutive_column_distance_avg_original", 0.0
            ),
            distance_avg_reorder=data.get(
                "2b_consecutive_column_distance_avg_reorder", 0.0
            ),
            distance_stdev_original=data.get(
                "2b_consecutive_column_distance_stdev_original", 0.0
            ),
            distance_stdev_reorder=data.get(
                "2b_consecutive_column_distance_stdev_reorder", 0.0
            ),
            compressibility_factor=data.get(
                "2b_metric_reordering_compressibility_factor", 1.0
            ),
            time_permutation_s=data.get("3_time_permutation(s)", 0.0),
            time_reorder_s=data.get("3_time_reorder(s)", 0.0),
        )

@dataclass
class CompressionData:
    from_permutation: str = ""
    input_path: str = ""
    invert_permutation: bool = False
    is_compressed: bool = False
    output_ef_path: str = ""
    output_path: str = ""
    user_permutation: bool = False
    blocksize_bytes: int = 0
    groupsize: int = 0
    nb_blocks: int = 0
    nb_cols: int = 0
    nb_rows: int = 0
    rows_per_block: int = 0
    target_blocksize_bytes: int = 0
    time_compression_s: float = 0.0
    time_reorder_s: float = 0.0
    histogram_original: List[int] = None
    histogram_reordered: List[int] = None
    
    def __post_init__(self):
        if self.histogram_original is None:
            self.histogram_original = []
        if self.histogram_reordered is None:
            self.histogram_reordered = []
    
    @classmethod
    def from_json(cls, data: dict) -> 'CompressionData':
        return cls(
            from_permutation=data.get("0_from_permutation", ""),
            input_path=data.get("0_input_path", ""),
            invert_permutation=data.get("0_invert_permutation", False),
            is_compressed=data.get("0_is_compressed", False),
            output_ef_path=data.get("0_output_ef_path", ""),
            output_path=data.get("0_output_path", ""),
            user_permutation=data.get("0_user_permutation", False),
            blocksize_bytes=data.get("1_blocksize(bytes)", 0),
            groupsize=data.get("1_groupsize", 0),
            nb_blocks=data.get("1_nb_blocks", 0),
            nb_cols=data.get("1_nb_cols", 0),
            nb_rows=data.get("1_nb_rows", 0),
            rows_per_block=data.get("1_rows_per_block", 0),
            target_blocksize_bytes=data.get("1_target_blocksize(bytes)", 0),
            time_compression_s=data.get("3_time_compression(s)", 0.0),
            time_reorder_s=data.get("3_time_reorder(s)", 0.0),
            histogram_original=data.get("4_histogram_original", []),
            histogram_reordered=data.get("4_histogram_reordered", [])
        )
    
@dataclass
class CompressionData:
    from_permutation: Optional[str] = None
    input_path: str = ""
    invert_permutation: bool = False
    is_compressed: bool = False
    output_ef_path: str = ""
    output_path: str = ""
    user_permutation: bool = False
    blocksize_bytes: int = 0
    groupsize: int = 0
    nb_blocks: Optional[int] = None
    nb_cols: int = 0
    nb_rows: int = 0
    rows_per_block: int = 0
    subsample_size: Optional[int] = None
    target_blocksize_bytes: int = 0
    time_compression_s: float = 0.0
    time_reorder_s: Optional[float] = None
    histogram_original: List[int] = field(default_factory=list)
    histogram_reordered: List[int] = field(default_factory=list)

    original_size_bytes: int = 0
    reordered_size_bytes: int = 0
    unordered_size_bytes: int = 0
   
    @classmethod
    def from_json(cls, data: dict) -> 'CompressionData':
        return cls(
            from_permutation=data.get("0_from_permutation"),
            input_path=data.get("0_input_path", ""),
            invert_permutation=data.get("0_invert_permutation", False),
            is_compressed=data.get("0_is_compressed", False),
            output_ef_path=data.get("0_output_ef_path", ""),
            output_path=data.get("0_output_path", ""),
            user_permutation=data.get("0_user_permutation", False),
            blocksize_bytes=data.get("1_blocksize(bytes)", 0),
            groupsize=data.get("1_groupsize", 0),
            nb_blocks=data.get("1_nb_blocks"),
            nb_cols=data.get("1_nb_cols", 0),
            nb_rows=data.get("1_nb_rows", 0),
            rows_per_block=data.get("1_rows_per_block", 0),
            subsample_size=data.get("1_subsample_size"),
            target_blocksize_bytes=data.get("1_target_blocksize(bytes)", 0),
            time_compression_s=data.get("3_time_compression(s)", 0.0),
            time_reorder_s=data.get("3_time_reorder(s)"),
            histogram_original=data.get("4_histogram_original", []),
            histogram_reordered=data.get("4_histogram_reordered", [])
        )
    
class CompressionMetrics:
    """"""
    index_id: str = None
    permutation_data: PermutationData = None
    compression_data: List[CompressionData] = None

