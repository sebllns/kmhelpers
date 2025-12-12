"""Operations for index compression and manipulation."""

from kmhelpers.operations.compressor import Compressor, CompressionParams
from kmhelpers.operations.fof import FofManager
from kmhelpers.operations.query import KmindexQuery, KmindexQueryResult
from kmhelpers.operations.sequence import Sequence, FASTAReader
from kmhelpers.operations.kmer import KmerOperation

__all__ = [
    "Compressor",
    "CompressionParams",
    "FofManager",
    "KmindexQuery",
    "KmindexQueryResult",
    "Sequence",
    "FASTAReader",
    "KmerOperation",
]
