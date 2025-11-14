import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

from kmhelpers.core.index import KmtricksIndex

@dataclass
class PermutationData:
    """
    Metrics related to column permutation computation and application.

    This class stores statistics about the permutation process, including
    distance metrics between columns and timing information.

    Attributes:
        input_path: Path to the input matrix file
        is_compressed: Whether the input matrix is compressed
        groupsize: Number of columns grouped together during permutation
        nb_cols: Number of columns (samples) in the matrix
        nb_rows: Number of rows (k-mers) in the matrix
        subsample_size: Number of rows used for computing the permutation
        computed_distances: Number of pairwise distances computed
        max_computable_distances: Maximum possible pairwise distances
        pct_computed_distances: Percentage of distances computed
        distance_avg_original: Average distance between consecutive columns before reordering
        distance_avg_reorder: Average distance between consecutive columns after reordering
        distance_stdev_original: Standard deviation of distances before reordering
        distance_stdev_reorder: Standard deviation of distances after reordering
        compressibility_factor: Estimated improvement in compressibility from reordering
        time_permutation_s: Time spent computing the permutation in seconds
        time_reorder_s: Time spent applying the permutation in seconds
    """

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
        """
        Create a PermutationData instance from a JSON dictionary.

        Args:
            data: Dictionary containing permutation metrics

        Returns:
            PermutationData instance populated with values from the dictionary
        """
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
    """
    Metrics related to matrix compression operations.

    This class stores statistics about the compression process, including
    block configuration, timing, and compression ratios.

    Attributes:
        from_permutation: Path to the permutation file used (if any)
        input_path: Path to the input matrix file
        invert_permutation: Whether the permutation was inverted
        is_compressed: Whether the input was already compressed
        output_ef_path: Path to the Elias-Fano encoded output file
        output_path: Path to the compressed output file
        user_permutation: Whether a user-provided permutation was used
        blocksize_bytes: Actual size of compression blocks in bytes
        groupsize: Number of columns grouped together
        nb_blocks: Number of blocks created
        nb_cols: Number of columns in the matrix
        nb_rows: Number of rows in the matrix
        rows_per_block: Number of rows per compression block
        subsample_size: Number of rows subsampled for permutation
        target_blocksize_bytes: Target size for compression blocks
        time_compression_s: Time spent on compression in seconds
        time_reorder_s: Time spent on reordering in seconds
        histogram_original: Histogram of bit patterns before reordering
        histogram_reordered: Histogram of bit patterns after reordering
        original_size_bytes: Size of original uncompressed matrix in bytes
        reordered_size_bytes: Size after compression with reordering in bytes
        unordered_size_bytes: Size after compression without reordering in bytes
    """

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
        """
        Create a CompressionData instance from a JSON dictionary.

        Args:
            data: Dictionary containing compression metrics

        Returns:
            CompressionData instance populated with values from the dictionary
        """
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
    """
    Container for all compression metrics from an index compression operation.

    This class aggregates permutation and compression metrics for an entire
    kmindex compression operation.

    Attributes:
        index_id: Identifier of the compressed index
        permutation_data: Metrics about the permutation computation
        compression_data: List of metrics for each compressed partition
    """

    index_id: str 
    permutation_data: PermutationData 
    compression_data: List[CompressionData] 

