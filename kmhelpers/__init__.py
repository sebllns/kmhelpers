"""
kmhelpers - K-mer Index Helpers

A Python toolkit for managing, compressing, and querying k-mer indices.
"""

__version__ = "0.5.3"

# Import core classes for easy access
from kmhelpers.core.utils import Main, Bin, Toolbox, Kmindex, BlockCompressorZSTD
from kmhelpers.core.index import KmtricksIndex, KmindexRegistry
from kmhelpers.core.wrapper import KmindexWrapper
from kmhelpers.core.bloom_filter import BloomFilterSpecs
from kmhelpers.operations.builder import IndexBuilder
from kmhelpers.operations.compressor import Compressor, CompressionParams
from kmhelpers.operations.fof import FofManager
from kmhelpers.operations.query import KmindexQuery, KmindexQueryResult
from kmhelpers.operations.sequence import Sequence
from kmhelpers.operations.kmer import KmerOperation
from kmhelpers.operations.fasta import Fasta, FASTAReader
from kmhelpers.operations.byte import ByteCounter, SizeFormat, SizeUnit

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
    "KmindexWrapper",
    "BloomFilterSpecs",

    # Operations - Builder
    "IndexBuilder",

    # Operations - Compression and Management
    "Compressor",
    "CompressionParams",
    "FofManager",

    # Operations - Query and Sequence
    "KmindexQuery",
    "KmindexQueryResult",
    "Sequence",
    "KmerOperation",

    # Operations - File Handling
    "Fasta",
    "FASTAReader",

    # Operations - Utilities
    "ByteCounter",
    "SizeFormat",
    "SizeUnit",
]
