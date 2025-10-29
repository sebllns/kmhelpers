"""
kmhelpers - K-mer Index Helpers

A Python toolkit for managing, compressing, and querying k-mer indices.
"""

__version__ = "0.0.1"

# Import core classes for easy access
from kmhelpers.core.utils import Main, Bin, Toolbox, Kmindex, BitmatrixShuffle, BlockCompressorZSTD
from kmhelpers.core.index import KmtricksIndex, KmindexRegistry
from kmhelpers.operations.compressor import Compressor, CompressionParams
from kmhelpers.metrics.compression_metrics import PermutationData, CompressionData, CompressionMetrics

__all__ = [
    # Core utilities
    "Main",
    "Bin",
    "Toolbox",
    "Kmindex",
    "BitmatrixShuffle",
    "BlockCompressorZSTD",

    # Index management
    "KmtricksIndex",
    "KmindexRegistry",

    # Compression
    "Compressor",
    "CompressionParams",

    # Metrics
    "PermutationData",
    "CompressionData",
    "CompressionMetrics",
]
