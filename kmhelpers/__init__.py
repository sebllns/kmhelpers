"""
kmhelpers - K-mer Index Helpers

A Python toolkit for managing, compressing, and querying k-mer indices.
"""

__version__ = "0.2.0"

# Import core classes for easy access
from kmhelpers.core.utils import Main, Bin, Toolbox, Kmindex, BlockCompressorZSTD
from kmhelpers.core.index import KmtricksIndex, KmindexRegistry
from kmhelpers.operations.compressor import Compressor, CompressionParams
from kmhelpers.metrics.compression_metrics import PermutationData, CompressionData, CompressionMetrics

__all__ = [
    # Core utilities
    "Main",
    "Bin",
    "Toolbox",
    "Kmindex",
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
