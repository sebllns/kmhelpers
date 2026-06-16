"""
kmhelpers - K-mer Index Helpers

A Python toolkit for managing, compressing, and querying k-mer indices.
"""

__version__ = "0.6.3.dev0"

from pykmhelpers.core.bloom_filter import BloomFilterSpecs
from pykmhelpers.core.byte import ByteCounter, SizeFormat, SizeUnit
from pykmhelpers.core.fasta import Fasta, FASTAReader
from pykmhelpers.core.index import KmindexRegistry, KmtricksIndex
from pykmhelpers.core.kmer import Kmer
from pykmhelpers.core.kmindex_wrapper import KmindexWrapper
from pykmhelpers.core.sequence import Sequence

# Import core classes for easy access
from pykmhelpers.core.utils import Bin, BlockCompressorZSTD, Kmindex, Main, Toolbox
from pykmhelpers.operations.builder import IndexBuilder
from pykmhelpers.operations.compressor import CompressionParams, Compressor
from pykmhelpers.pipeline.fof import FofManager
from pykmhelpers.pipeline.query import KmindexQuery, KmindexQueryResult

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
