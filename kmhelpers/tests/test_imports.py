"""Test that all kmhelpers classes can be imported correctly."""

import unittest


class TestDirectImports(unittest.TestCase):
    """Test importing directly from submodules."""

    def test_core_utils_imports(self):
        """Test importing from kmhelpers.core.utils"""
        from kmhelpers.core.utils import Main, Bin, Toolbox, Kmindex, BlockCompressorZSTD
        self.assertIsNotNone(Main)
        self.assertIsNotNone(Bin)
        self.assertIsNotNone(Toolbox)
        self.assertIsNotNone(Kmindex)
        self.assertIsNotNone(BlockCompressorZSTD)

    def test_core_index_imports(self):
        """Test importing from kmhelpers.core.index"""
        from kmhelpers.core.index import KmtricksIndex, KmindexRegistry
        self.assertIsNotNone(KmtricksIndex)
        self.assertIsNotNone(KmindexRegistry)

    def test_core_wrapper_imports(self):
        """Test importing from kmhelpers.core.wrapper"""
        from kmhelpers.core.wrapper import KmindexWrapper
        self.assertIsNotNone(KmindexWrapper)

    def test_core_bloom_filter_imports(self):
        """Test importing from kmhelpers.core.bloom_filter"""
        from kmhelpers.core.bloom_filter import BloomFilterSpecs
        self.assertIsNotNone(BloomFilterSpecs)

    def test_operations_builder_imports(self):
        """Test importing from kmhelpers.operations.builder"""
        from kmhelpers.operations.builder import IndexBuilder
        self.assertIsNotNone(IndexBuilder)

    def test_operations_compressor_imports(self):
        """Test importing from kmhelpers.operations.compressor"""
        from kmhelpers.operations.compressor import Compressor, CompressionParams
        self.assertIsNotNone(Compressor)
        self.assertIsNotNone(CompressionParams)

    def test_operations_fof_imports(self):
        """Test importing from kmhelpers.operations.fof"""
        from kmhelpers.operations.fof import FofManager
        self.assertIsNotNone(FofManager)

    def test_operations_query_imports(self):
        """Test importing from kmhelpers.operations.query"""
        from kmhelpers.operations.query import KmindexQuery, KmindexQueryResult
        self.assertIsNotNone(KmindexQuery)
        self.assertIsNotNone(KmindexQueryResult)

    def test_operations_sequence_imports(self):
        """Test importing from kmhelpers.operations.sequence"""
        from kmhelpers.operations.sequence import Sequence
        self.assertIsNotNone(Sequence)

    def test_operations_kmer_imports(self):
        """Test importing from kmhelpers.operations.kmer"""
        from kmhelpers.operations.kmer import KmerOperation
        self.assertIsNotNone(KmerOperation)

    def test_operations_fasta_imports(self):
        """Test importing from kmhelpers.operations.fasta"""
        from kmhelpers.operations.fasta import Fasta, FASTAReader
        self.assertIsNotNone(Fasta)
        self.assertIsNotNone(FASTAReader)

    def test_operations_byte_imports(self):
        """Test importing from kmhelpers.operations.byte"""
        from kmhelpers.operations.byte import ByteCounter, SizeFormat, SizeUnit
        self.assertIsNotNone(ByteCounter)
        self.assertIsNotNone(SizeFormat)
        self.assertIsNotNone(SizeUnit)


class TestCorePackageImports(unittest.TestCase):
    """Test importing from kmhelpers.core package."""

    def test_all_core_imports(self):
        """Test importing all classes from kmhelpers.core"""
        from kmhelpers.core import (
            Main, Bin, Toolbox, Kmindex, BlockCompressorZSTD,
            KmtricksIndex, KmindexRegistry, KmindexWrapper,
            BloomFilterSpecs
        )
        self.assertIsNotNone(Main)
        self.assertIsNotNone(Bin)
        self.assertIsNotNone(Toolbox)
        self.assertIsNotNone(Kmindex)
        self.assertIsNotNone(BlockCompressorZSTD)
        self.assertIsNotNone(KmtricksIndex)
        self.assertIsNotNone(KmindexRegistry)
        self.assertIsNotNone(KmindexWrapper)
        self.assertIsNotNone(BloomFilterSpecs)


class TestOperationsPackageImports(unittest.TestCase):
    """Test importing from kmhelpers.operations package."""

    def test_all_operations_imports(self):
        """Test importing all classes from kmhelpers.operations"""
        from kmhelpers.operations import (
            IndexBuilder,
            Compressor, CompressionParams,
            Fasta, FASTAReader,
            FofManager,
            KmindexQuery, KmindexQueryResult,
            Sequence,
            KmerOperation,
            ByteCounter, SizeFormat, SizeUnit
        )
        self.assertIsNotNone(IndexBuilder)
        self.assertIsNotNone(Compressor)
        self.assertIsNotNone(CompressionParams)
        self.assertIsNotNone(Fasta)
        self.assertIsNotNone(FASTAReader)
        self.assertIsNotNone(FofManager)
        self.assertIsNotNone(KmindexQuery)
        self.assertIsNotNone(KmindexQueryResult)
        self.assertIsNotNone(Sequence)
        self.assertIsNotNone(KmerOperation)
        self.assertIsNotNone(ByteCounter)
        self.assertIsNotNone(SizeFormat)
        self.assertIsNotNone(SizeUnit)


class TestTopLevelImports(unittest.TestCase):
    """Test importing from kmhelpers top-level package."""

    def test_all_top_level_imports(self):
        """Test importing all classes from kmhelpers"""
        from kmhelpers import (
            # Core
            Main, Bin, Toolbox, Kmindex, BlockCompressorZSTD,
            KmtricksIndex, KmindexRegistry, KmindexWrapper,
            BloomFilterSpecs,
            # Operations
            IndexBuilder,
            Compressor, CompressionParams,
            Fasta, FASTAReader,
            FofManager,
            KmindexQuery, KmindexQueryResult,
            Sequence,
            KmerOperation,
            ByteCounter, SizeFormat, SizeUnit
        )
        # Verify all are accessible
        self.assertIsNotNone(Main)
        self.assertIsNotNone(Bin)
        self.assertIsNotNone(Toolbox)
        self.assertIsNotNone(Kmindex)
        self.assertIsNotNone(BlockCompressorZSTD)
        self.assertIsNotNone(KmtricksIndex)
        self.assertIsNotNone(KmindexRegistry)
        self.assertIsNotNone(KmindexWrapper)
        self.assertIsNotNone(BloomFilterSpecs)
        self.assertIsNotNone(IndexBuilder)
        self.assertIsNotNone(Compressor)
        self.assertIsNotNone(CompressionParams)
        self.assertIsNotNone(Fasta)
        self.assertIsNotNone(FASTAReader)
        self.assertIsNotNone(FofManager)
        self.assertIsNotNone(KmindexQuery)
        self.assertIsNotNone(KmindexQueryResult)
        self.assertIsNotNone(Sequence)
        self.assertIsNotNone(KmerOperation)
        self.assertIsNotNone(ByteCounter)
        self.assertIsNotNone(SizeFormat)
        self.assertIsNotNone(SizeUnit)

    def test_star_import(self):
        """Test that star import works"""
        import kmhelpers
        # Verify __all__ is defined
        self.assertTrue(hasattr(kmhelpers, '__all__'))
        self.assertGreater(len(kmhelpers.__all__), 0)


if __name__ == '__main__':
    unittest.main()
