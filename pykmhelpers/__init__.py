"""
kmhelpers - K-mer Index Helpers

A Python toolkit for managing, compressing, and querying k-mer indices.
"""

__version__ = "0.6.0"

# Import core classes for easy access
from pykmhelpers.core.utils import Main, Bin, Toolbox, Kmindex, BlockCompressorZSTD
from pykmhelpers.core.index import KmtricksIndex, KmindexRegistry
from pykmhelpers.core.wrapper import KmindexWrapper
from pykmhelpers.core.bloom_filter import BloomFilterSpecs
from pykmhelpers.operations.builder import IndexBuilder
from pykmhelpers.operations.compressor import Compressor, CompressionParams
from pykmhelpers.operations.fof import FofManager
from pykmhelpers.operations.query import KmindexQuery, KmindexQueryResult
from pykmhelpers.core.sequence import Sequence
from pykmhelpers.core.kmer import Kmer
from pykmhelpers.operations.fasta import Fasta, FASTAReader
from pykmhelpers.core.byte import ByteCounter, SizeFormat, SizeUnit

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
    "Kmer",

    # Operations - File Handling
    "Fasta",
    "FASTAReader",

    # Operations - Utilities
    "ByteCounter",
    "SizeFormat",
    "SizeUnit",
]
