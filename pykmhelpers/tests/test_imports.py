"""Test that all kmhelpers classes can be imported correctly."""

import unittest


class TestDirectImports(unittest.TestCase):
    """Test importing directly from submodules."""

    def test_core_utils_imports(self):
        """Test importing from pykmhelpers.core.utils"""
        from pykmhelpers.core.utils import Main, Bin, Toolbox, Kmindex, BlockCompressorZSTD
        self.assertIsNotNone(Main)
        self.assertIsNotNone(Bin)
        self.assertIsNotNone(Toolbox)
        self.assertIsNotNone(Kmindex)
        self.assertIsNotNone(BlockCompressorZSTD)

    def test_core_index_imports(self):
        """Test importing from pykmhelpers.core.index"""
        from pykmhelpers.core.index import KmtricksIndex, KmindexRegistry
        self.assertIsNotNone(KmtricksIndex)
        self.assertIsNotNone(KmindexRegistry)

    def test_core_wrapper_imports(self):
        """Test importing from pykmhelpers.core.wrapper"""
        from pykmhelpers.core.kmindex_wrapper import KmindexWrapper
        self.assertIsNotNone(KmindexWrapper)

    def test_core_bloom_filter_imports(self):
        """Test importing from pykmhelpers.core.bloom_filter"""
        from pykmhelpers.core.bloom_filter import BloomFilterSpecs, SpanManager
        self.assertIsNotNone(BloomFilterSpecs)
        self.assertIsNotNone(SpanManager)

    def test_core_kmer_imports(self):
        """Test importing from pykmhelpers.core.kmer"""
        from pykmhelpers.core.kmer import Kmer
        self.assertIsNotNone(Kmer)

    def test_operations_builder_imports(self):
        """Test importing from pykmhelpers.operations.builder"""
        from pykmhelpers.operations.builder import IndexBuilder
        self.assertIsNotNone(IndexBuilder)

    def test_pipeline_fof_imports(self):
        """Test importing from pykmhelpers.pipeline.fof"""
        from pykmhelpers.pipeline.fof import FofManager
        self.assertIsNotNone(FofManager)

    def test_pipeline_query_imports(self):
        """Test importing from pykmhelpers.pipeline.query"""
        from pykmhelpers.pipeline.query import (
            KmindexQuery,
            KmindexQueryResult,
            QueryRunner,
            QueryRunnerConfig,
        )
        self.assertIsNotNone(KmindexQuery)
        self.assertIsNotNone(KmindexQueryResult)
        self.assertIsNotNone(QueryRunner)
        self.assertIsNotNone(QueryRunnerConfig)

    def test_core_sequence_imports(self):
        """Test importing from pykmhelpers.core.sequence"""
        from pykmhelpers.core.sequence import Sequence
        self.assertIsNotNone(Sequence)

    def test_core_fasta_imports(self):
        """Test importing from pykmhelpers.core.fasta"""
        from pykmhelpers.core.fasta import Fasta, FASTAReader
        self.assertIsNotNone(Fasta)
        self.assertIsNotNone(FASTAReader)

    def test_core_byte_imports(self):
        """Test importing from pykmhelpers.core.byte"""
        from pykmhelpers.core.byte import ByteCounter, SizeFormat, SizeUnit
        self.assertIsNotNone(ByteCounter)
        self.assertIsNotNone(SizeFormat)
        self.assertIsNotNone(SizeUnit)


class TestCorePackageImports(unittest.TestCase):
    """Test importing from pykmhelpers.core package."""

    def test_all_core_imports(self):
        """Test importing all classes from pykmhelpers.core"""
        from pykmhelpers.core import (
            Main, Bin, Toolbox, Kmindex, BlockCompressorZSTD,
            KmtricksIndex, KmindexRegistry, KmindexWrapper,
            BloomFilterSpecs, SpanManager, Kmer, Sequence
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
        self.assertIsNotNone(SpanManager)
        self.assertIsNotNone(Kmer)
        self.assertIsNotNone(Sequence)


class TestOperationsPackageImports(unittest.TestCase):
    """Test importing from pykmhelpers.operations package."""

    def test_all_operations_imports(self):
        """Test importing all classes from pykmhelpers.operations"""
        from pykmhelpers.operations import (
            IndexBuilder,
            Fasta, FASTAReader,
            FofManager,
            KmindexQuery, KmindexQueryResult,
            ByteCounter, SizeFormat, SizeUnit
        )
        self.assertIsNotNone(IndexBuilder)
        self.assertIsNotNone(Fasta)
        self.assertIsNotNone(FASTAReader)
        self.assertIsNotNone(FofManager)
        self.assertIsNotNone(KmindexQuery)
        self.assertIsNotNone(KmindexQueryResult)
        self.assertIsNotNone(ByteCounter)
        self.assertIsNotNone(SizeFormat)
        self.assertIsNotNone(SizeUnit)


class TestTopLevelImports(unittest.TestCase):
    """Test importing from pykmhelpers top-level package."""

    def test_all_top_level_imports(self):
        """Test importing all classes from pykmhelpers"""
        from pykmhelpers import (
            # Core
            Main, Bin, Toolbox, Kmindex, BlockCompressorZSTD,
            KmtricksIndex, KmindexRegistry, KmindexWrapper,
            BloomFilterSpecs,
            # Operations
            IndexBuilder,
            Fasta, FASTAReader,
            FofManager,
            KmindexQuery, KmindexQueryResult,
            QueryRunner, QueryRunnerConfig,
            Sequence, Kmer,
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
        self.assertIsNotNone(Fasta)
        self.assertIsNotNone(FASTAReader)
        self.assertIsNotNone(FofManager)
        self.assertIsNotNone(KmindexQuery)
        self.assertIsNotNone(KmindexQueryResult)
        self.assertIsNotNone(QueryRunner)
        self.assertIsNotNone(QueryRunnerConfig)
        self.assertIsNotNone(Sequence)
        self.assertIsNotNone(Kmer)
        self.assertIsNotNone(ByteCounter)
        self.assertIsNotNone(SizeFormat)
        self.assertIsNotNone(SizeUnit)

    def test_star_import(self):
        """Test that star import works"""
        import pykmhelpers
        # Verify __all__ is defined
        self.assertTrue(hasattr(pykmhelpers, '__all__'))
        self.assertGreater(len(pykmhelpers.__all__), 0)

    def test_new_v063_exports_in_all(self):
        """Test that the classes exported in 0.6.3 are listed in __all__."""
        import pykmhelpers
        for name in ("Kmer", "QueryRunner", "QueryRunnerConfig"):
            self.assertIn(name, pykmhelpers.__all__)


if __name__ == '__main__':
    unittest.main()
