"""
Unit tests for KmtricksIndex and KmindexRegistry classes.

This module contains comprehensive tests for the index management functionality,
including creating, loading, manipulating, and managing kmtricks indices.
"""

import json
import os
import shutil
import tarfile
import tempfile
import unittest
from pathlib import Path

from pykmhelpers.core.index import (
    IndexCompressionState,
    KmindexRegistry,
    KmtricksIndex,
    NotAnIndexError,
)
from pykmhelpers.core.kmindex_layout import create_empty_index_json


class TestKmtricksIndexBase(unittest.TestCase):
    """Base test class with shared setup and teardown for KmtricksIndex tests."""

    @classmethod
    def setUpClass(cls):
        """Set up test fixtures that are used across all tests."""
        # Locate the test data archive
        cls.project_root = Path(__file__).parent.parent.parent
        cls.test_data_tar = (
            cls.project_root / "examples" / "data" / "SYNTHETIC_ROD_10.tar"
        )
        cls.test_data_dir = cls.project_root / "examples" / "data" / "SYNTHETIC_ROD_10"

        # Verify test data exists
        if not cls.test_data_dir.exists():
            if cls.test_data_tar.exists():
                # Extract the tar archive
                print(f"Extracting test data from {cls.test_data_tar}")
                with tarfile.open(cls.test_data_tar, "r") as tar:
                    tar.extractall(path=cls.test_data_tar.parent)
            else:
                raise FileNotFoundError(
                    f"Test data not found: {cls.test_data_tar} or {cls.test_data_dir}"
                )

    def setUp(self):
        """Set up test fixtures for each test method."""
        # Create a temporary directory for test operations
        self.temp_dir = tempfile.mkdtemp(prefix="kmhelpers_test_")
        self.temp_path = Path(self.temp_dir)

        # Copy test index to temp directory
        self.test_index_id = "SYNTHETIC_ROD_10"
        self.test_index_path = self.temp_path / self.test_index_id
        shutil.copytree(self.test_data_dir, self.test_index_path)

        # Create separate directories for registry tests
        self.registry_path = self.temp_path / "registry"
        self.registry_path.mkdir(exist_ok=True)

        # Create a source directory for indices to be registered
        self.source_path = self.temp_path / "source"
        self.source_path.mkdir(exist_ok=True)

        # Copy the test index to source directory (not registry)
        self.source_index_path = self.source_path / self.test_index_id
        shutil.copytree(self.test_data_dir, self.source_index_path)

        # Create index.json for registry
        create_empty_index_json(str(self.registry_path))

    def tearDown(self):
        """Clean up test fixtures after each test method."""
        # Remove temporary directory
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)


class TestKmtricksIndexInitialization(TestKmtricksIndexBase):
    """Tests for KmtricksIndex initialization and basic properties."""

    def test_init_with_valid_index(self):
        """Test initialization with a valid index directory."""
        index = KmtricksIndex(str(self.temp_path), self.test_index_id)
        self.assertEqual(index.id, self.test_index_id)
        self.assertEqual(index.parent_dir, str(self.temp_path))
        self.assertEqual(index.compress_state, IndexCompressionState.UNKNOWN)

    def test_init_with_compression_state(self):
        """Test initialization with specific compression state."""
        index = KmtricksIndex(
            str(self.temp_path),
            self.test_index_id,
            compressed_state=IndexCompressionState.COMPRESSED,
        )
        self.assertEqual(index.compress_state, IndexCompressionState.COMPRESSED)

    def test_init_with_nonexistent_index(self):
        """Test initialization with non-existent index raises error."""
        with self.assertRaises(NotADirectoryError):
            KmtricksIndex(str(self.temp_path), "nonexistent_index")

    def test_dir_path_property(self):
        """Test dir_path property returns correct path."""
        index = KmtricksIndex(str(self.temp_path), self.test_index_id)
        expected_path = os.path.join(str(self.temp_path), self.test_index_id)
        self.assertEqual(index.dir_path, expected_path)

    def test_fof_path_property(self):
        """Test fof_path property returns correct path."""
        index = KmtricksIndex(str(self.temp_path), self.test_index_id)
        self.assertTrue(index.fof_path.endswith("kmtricks.fof"))

    def test_matrices_dir_path_property(self):
        """Test matrices_dir_path property returns correct path."""
        index = KmtricksIndex(str(self.temp_path), self.test_index_id)
        self.assertTrue(index.matrices_dir_path.endswith("matrices"))


class TestKmtricksIndexLoading(TestKmtricksIndexBase):
    """Tests for loading index properties from files."""

    def test_load_kmtricks_index(self):
        """Test loading index properties from kmtricks files."""
        index = KmtricksIndex(str(self.temp_path), self.test_index_id)
        index.load_kmtricks_index()

        # Verify properties were loaded
        self.assertGreater(index.nb_samples, 0)
        self.assertGreater(index.nb_partitions, 0)
        self.assertGreater(index.kmer_size, 0)
        self.assertGreater(index.bloom_size, 0)
        self.assertGreater(len(index.samples), 0)

    def test_load_kmtricks_index_missing_options(self):
        """Test loading fails when options.txt is missing."""
        # auto_load=False so load runs after we remove the file (a loaded index
        # short-circuits load_kmtricks_index without re-checking files).
        index = KmtricksIndex(str(self.temp_path), self.test_index_id, auto_load=False)
        options_path = os.path.join(index.dir_path, "options.txt")
        os.remove(options_path)

        with self.assertRaises(FileNotFoundError):
            index.load_kmtricks_index()

    def test_load_kmtricks_index_missing_fof(self):
        """Test loading fails when kmtricks.fof is missing."""
        index = KmtricksIndex(str(self.temp_path), self.test_index_id, auto_load=False)
        fof_path = os.path.join(index.dir_path, "kmtricks.fof")
        os.remove(fof_path)

        with self.assertRaises(FileNotFoundError):
            index.load_kmtricks_index()

    def test_property_access_after_loading(self):
        """Test accessing properties after loading."""
        index = KmtricksIndex(str(self.temp_path), self.test_index_id)
        index.load_kmtricks_index()

        # Test individual properties
        self.assertIsInstance(index.nb_samples, int)
        self.assertIsInstance(index.nb_partitions, int)
        self.assertIsInstance(index.samples, list)
        self.assertIsInstance(index.kmer_size, int)
        self.assertIsInstance(index.bloom_size, int)


class TestKmtricksIndexProperties(TestKmtricksIndexBase):
    """Tests for index property management."""

    def test_set_property(self):
        """Test setting a property."""
        index = KmtricksIndex(str(self.temp_path), self.test_index_id)
        result = index.set_property("test_key", "test_value")
        self.assertTrue(result)
        self.assertEqual(index.get_property("test_key"), "test_value")

    def test_get_property_existing(self):
        """Test getting an existing property."""
        index = KmtricksIndex(str(self.temp_path), self.test_index_id)
        index.set_property("test_key", "test_value")
        value = index.get_property("test_key")
        self.assertEqual(value, "test_value")

    def test_get_property_nonexistent(self):
        """Test getting a non-existent property raises KeyError."""
        index = KmtricksIndex(str(self.temp_path), self.test_index_id)
        with self.assertRaises(KeyError):
            index.get_property("nonexistent_key")

    def test_get_all_properties(self):
        """Test getting all properties."""
        index = KmtricksIndex(str(self.temp_path), self.test_index_id)
        index.set_property("test_key", "test_value")
        props = index.get_all_properties()
        self.assertIsInstance(props, dict)
        self.assertIn("test_key", props)

    def test_import_properties(self):
        """Test importing properties from a dictionary."""
        index = KmtricksIndex(str(self.temp_path), self.test_index_id)
        props = {"key1": "value1", "key2": 123, "key3": [1, 2, 3]}
        index.import_properties(props)

        self.assertEqual(index.get_property("key1"), "value1")
        self.assertEqual(index.get_property("key2"), 123)
        self.assertEqual(index.get_property("key3"), [1, 2, 3])


class TestKmtricksIndexMatrixOperations(TestKmtricksIndexBase):
    """Tests for matrix-related operations."""

    def test_get_matrix_path(self):
        """Test getting matrix path for a partition."""
        index = KmtricksIndex(str(self.temp_path), self.test_index_id)
        path = index.get_matrix_path(0)
        self.assertTrue(path.endswith("matrix_0.cmbf"))

    def test_get_matrix_path_compressed(self):
        """Test getting compressed matrix path."""
        index = KmtricksIndex(str(self.temp_path), self.test_index_id)
        path = index.get_matrix_path(0, is_compressed=True)
        self.assertTrue(path.endswith("blocks_0"))

    def test_get_matrix_byte_size(self):
        """Test getting matrix byte size."""
        index = KmtricksIndex(str(self.temp_path), self.test_index_id)
        size = index.get_matrix_byte_size(0)
        self.assertGreater(size, 0)

    def test_get_matrix_row_count(self):
        """Test getting matrix row count."""
        index = KmtricksIndex(str(self.temp_path), self.test_index_id)
        index.load_kmtricks_index()
        row_count = index.get_matrix_row_count(0)
        self.assertGreater(row_count, 0)

    def test_get_matrix_element_count(self):
        """Test getting matrix element count."""
        index = KmtricksIndex(str(self.temp_path), self.test_index_id)
        index.load_kmtricks_index()
        element_count = index.get_matrix_element_count(0)
        self.assertGreater(element_count, 0)

    def test_get_matrix_size(self):
        """Test getting matrix dimensions."""
        index = KmtricksIndex(str(self.temp_path), self.test_index_id)
        index.load_kmtricks_index()
        rows, cols = index.get_matrix_size()
        self.assertGreater(rows, 0)
        self.assertGreater(cols, 0)
        self.assertEqual(cols, index.nb_samples)

    def test_bytes_per_row(self):
        """Test bytes_per_row property."""
        index = KmtricksIndex(str(self.temp_path), self.test_index_id)
        index.load_kmtricks_index()
        bpr = index.bytes_per_row
        self.assertGreater(bpr, 0)

    def test_header_size(self):
        """Test header_size property."""
        index = KmtricksIndex(str(self.temp_path), self.test_index_id)
        header_size = index.header_size
        self.assertEqual(header_size, 49)


class TestKmtricksIndexStructureCheck(TestKmtricksIndexBase):
    """Tests for index structure validation."""

    def test_check_structure_valid(self):
        """Test structure check on valid index."""
        index = KmtricksIndex(str(self.temp_path), self.test_index_id)
        index.load_kmtricks_index()
        result = index.check_structure()
        self.assertTrue(result)

    def test_check_structure_invalid_properties(self):
        """Test structure check with invalid properties."""
        index = KmtricksIndex(str(self.temp_path), self.test_index_id)
        index.load_kmtricks_index()
        # Set invalid property
        index.set_property("bloom_size", 0)
        result = index.check_structure()
        self.assertFalse(result)


class TestKmtricksIndexCopyMove(TestKmtricksIndexBase):
    """Tests for copy_to and move_to operations."""

    def test_copy_to_valid_destination(self):
        """Test copying index to a new destination."""
        index = KmtricksIndex(str(self.temp_path), self.test_index_id)
        dest_path = self.temp_path / "copy_dest"
        dest_path.mkdir()

        result = index.copy_to(str(dest_path))
        self.assertTrue(result)

        # Verify the copy exists
        copied_index_path = dest_path / self.test_index_id
        self.assertTrue(copied_index_path.exists())
        self.assertTrue((copied_index_path / "kmtricks.fof").exists())

        # Verify original still exists
        self.assertTrue(self.test_index_path.exists())

    def test_copy_to_nonexistent_destination(self):
        """Test copying to a destination that doesn't exist (should be created)."""
        index = KmtricksIndex(str(self.temp_path), self.test_index_id)
        dest_path = self.temp_path / "new_dest"

        result = index.copy_to(str(dest_path))
        self.assertTrue(result)
        self.assertTrue(dest_path.exists())
        self.assertTrue((dest_path / self.test_index_id).exists())

    def test_copy_to_existing_destination(self):
        """Test copying to a destination where index already exists."""
        index = KmtricksIndex(str(self.temp_path), self.test_index_id)
        dest_path = self.temp_path / "copy_dest"
        dest_path.mkdir()

        # First copy should succeed
        result1 = index.copy_to(str(dest_path))
        self.assertTrue(result1)

        # Second copy should fail
        result2 = index.copy_to(str(dest_path))
        self.assertFalse(result2)

    def test_move_to_valid_destination(self):
        """Test moving index to a new destination."""
        index = KmtricksIndex(str(self.temp_path), self.test_index_id)
        original_path = Path(index.dir_path)
        dest_path = self.temp_path / "move_dest"
        dest_path.mkdir()

        result = index.move_to(str(dest_path))
        self.assertTrue(result)

        # Verify the move
        moved_index_path = dest_path / self.test_index_id
        self.assertTrue(moved_index_path.exists())
        self.assertFalse(original_path.exists())

        # Verify parent_dir was updated
        self.assertEqual(index.parent_dir, str(dest_path))

    def test_move_to_nonexistent_destination(self):
        """Test moving to a destination that doesn't exist (should be created)."""
        index = KmtricksIndex(str(self.temp_path), self.test_index_id)
        dest_path = self.temp_path / "new_move_dest"

        result = index.move_to(str(dest_path))
        self.assertTrue(result)
        self.assertTrue(dest_path.exists())
        self.assertTrue((dest_path / self.test_index_id).exists())

    def test_move_to_existing_destination(self):
        """Test moving to a destination where index already exists.

        move_to() must honor copy_to()'s result: when the destination already
        exists the copy fails, so the move must abort (return False) and leave
        the source index intact rather than destroying it.
        """
        index = KmtricksIndex(str(self.temp_path), self.test_index_id)
        original_path = Path(index.dir_path)
        dest_path = self.temp_path / "move_dest"
        dest_path.mkdir()

        # Create a duplicate at destination
        shutil.copytree(self.test_index_path, dest_path / self.test_index_id)

        # Move should fail (destination already exists)
        result = index.move_to(str(dest_path))
        self.assertFalse(result)
        # Source index must not have been destroyed
        self.assertTrue(original_path.exists())


class TestKmtricksIndexIteration(TestKmtricksIndexBase):
    """Tests for iteration over the index (yields sample names)."""

    def test_iterate_over_samples(self):
        """Test iterating over an index yields its sample names."""
        index = KmtricksIndex(str(self.temp_path), self.test_index_id)
        index.load_kmtricks_index()

        samples = list(index)
        self.assertEqual(len(samples), index.nb_samples)
        self.assertEqual(samples, index.samples)
        self.assertTrue(all(isinstance(s, str) for s in samples))


class TestKmtricksIndexStringRepresentation(TestKmtricksIndexBase):
    """Tests for string representations."""

    def test_str_representation(self):
        """Test __str__ method."""
        index = KmtricksIndex(str(self.temp_path), self.test_index_id)
        index.load_kmtricks_index()
        str_repr = str(index)
        self.assertIn(self.test_index_id, str_repr)
        self.assertIn("Index", str_repr)

    def test_repr_representation(self):
        """Test __repr__ method."""
        index = KmtricksIndex(str(self.temp_path), self.test_index_id)
        repr_str = repr(index)
        self.assertIn(self.test_index_id, repr_str)
        self.assertIn("Index", repr_str)


class TestKmindexRegistry(TestKmtricksIndexBase):
    """Tests for KmindexRegistry class."""

    def test_init_creates_json_if_missing(self):
        """Test registry creates index.json if it doesn't exist."""
        new_registry_path = self.temp_path / "new_registry"
        new_registry_path.mkdir()

        KmindexRegistry(str(new_registry_path))
        self.assertTrue((new_registry_path / "index.json").exists())

    def test_init_with_existing_json(self):
        """Test registry initialization with existing index.json."""
        registry = KmindexRegistry(str(self.registry_path))
        self.assertEqual(registry._root_path, str(self.registry_path))

    def test_json_path_property(self):
        """Test json_path property."""
        registry = KmindexRegistry(str(self.registry_path))
        expected_path = os.path.join(str(self.registry_path), "index.json")
        self.assertEqual(registry.json_path, expected_path)

    def test_json_exists_property(self):
        """Test json_exists property."""
        registry = KmindexRegistry(str(self.registry_path))
        self.assertTrue(registry.json_exists)

    def test_list_indices_empty(self):
        """Test listing indices in empty registry."""
        new_registry_path = self.temp_path / "empty_registry"
        new_registry_path.mkdir()
        registry = KmindexRegistry(str(new_registry_path))
        indices = registry.list_indices()
        self.assertEqual(len(indices), 0)

    def test_add_index(self):
        """Test adding an index to the registry."""
        registry = KmindexRegistry(str(self.registry_path))
        index = KmtricksIndex(str(self.source_path), self.test_index_id)
        index.load_kmtricks_index()

        result = registry.add_index(index)
        self.assertTrue(result)
        self.assertIn(self.test_index_id, registry.list_indices())

    def test_add_index_duplicate(self):
        """Test adding a duplicate index returns False."""
        registry = KmindexRegistry(str(self.registry_path))
        index = KmtricksIndex(str(self.source_path), self.test_index_id)
        index.load_kmtricks_index()

        result1 = registry.add_index(index)
        self.assertTrue(result1)

        result2 = registry.add_index(index)
        self.assertFalse(result2)

    def test_has_index(self):
        """Test checking if an index exists."""
        registry = KmindexRegistry(str(self.registry_path))
        index = KmtricksIndex(str(self.source_path), self.test_index_id)
        index.load_kmtricks_index()

        self.assertFalse(registry.has_index(self.test_index_id))
        registry.add_index(index)
        self.assertTrue(registry.has_index(self.test_index_id))

    def test_get_index(self):
        """Test getting an index from the registry."""
        registry = KmindexRegistry(str(self.registry_path))
        index = KmtricksIndex(str(self.source_path), self.test_index_id)
        index.load_kmtricks_index()
        registry.add_index(index)

        retrieved_index = registry.get_index(self.test_index_id)
        self.assertIsInstance(retrieved_index, KmtricksIndex)
        self.assertEqual(retrieved_index.id, self.test_index_id)

    def test_get_index_nonexistent(self):
        """Test getting a non-existent index raises KeyError."""
        registry = KmindexRegistry(str(self.registry_path))
        with self.assertRaises(KeyError):
            registry.get_index("nonexistent_index")

    def test_get_index_properties(self):
        """Test getting index properties."""
        registry = KmindexRegistry(str(self.registry_path))
        index = KmtricksIndex(str(self.source_path), self.test_index_id)
        index.load_kmtricks_index()
        registry.add_index(index)

        props = registry.get_index_properties(self.test_index_id)
        self.assertIsInstance(props, dict)
        self.assertIn("nb_samples", props)

    def test_remove_index(self):
        """Test removing an index from the registry."""
        registry = KmindexRegistry(str(self.registry_path))
        index = KmtricksIndex(str(self.source_path), self.test_index_id)
        index.load_kmtricks_index()
        registry.add_index(index)

        result = registry.remove_index(self.test_index_id)
        self.assertTrue(result)
        self.assertFalse(registry.has_index(self.test_index_id))

    def test_remove_index_nonexistent(self):
        """Test removing a non-existent index returns False."""
        registry = KmindexRegistry(str(self.registry_path))
        result = registry.remove_index("nonexistent_index")
        self.assertFalse(result)

    def test_remove_index_updates_json(self):
        """Test that removing an index updates the JSON file."""
        registry = KmindexRegistry(str(self.registry_path))
        index = KmtricksIndex(str(self.source_path), self.test_index_id)
        index.load_kmtricks_index()
        registry.add_index(index)

        registry.remove_index(self.test_index_id)

        # Read JSON file directly to verify
        with open(registry.json_path, "r") as f:
            data = json.load(f)
        self.assertNotIn(self.test_index_id, data["index"])

    def test_iterate_over_indices(self):
        """Test iterating over all indices in the registry."""
        registry = KmindexRegistry(str(self.registry_path))
        index = KmtricksIndex(str(self.source_path), self.test_index_id)
        index.load_kmtricks_index()
        registry.add_index(index)

        indices = list(registry)
        self.assertEqual(len(indices), 1)
        self.assertIsInstance(indices[0], KmtricksIndex)

    def test_len(self):
        """Test __len__ method."""
        registry = KmindexRegistry(str(self.registry_path))
        self.assertEqual(len(registry), 0)

        index = KmtricksIndex(str(self.source_path), self.test_index_id)
        index.load_kmtricks_index()
        registry.add_index(index)
        self.assertEqual(len(registry), 1)

    def test_str_representation(self):
        """Test __str__ method."""
        registry = KmindexRegistry(str(self.registry_path))
        str_repr = str(registry)
        self.assertIn("IndexRegistry", str_repr)
        self.assertIn(str(self.registry_path), str_repr)

    def test_getitem(self):
        """Test __getitem__ method."""
        registry = KmindexRegistry(str(self.registry_path))
        index = KmtricksIndex(str(self.source_path), self.test_index_id)
        index.load_kmtricks_index()
        registry.add_index(index)

        retrieved = registry[self.test_index_id]
        self.assertIsInstance(retrieved, KmtricksIndex)
        if retrieved is not None:
            self.assertEqual(retrieved.id, self.test_index_id)

    def test_getitem_nonexistent(self):
        """Test __getitem__ with non-existent index returns None."""
        registry = KmindexRegistry(str(self.registry_path))
        result = registry["nonexistent_index"]
        self.assertIsNone(result)

    def test_setitem(self):
        """Test __setitem__ method."""
        registry = KmindexRegistry(str(self.registry_path))
        index = KmtricksIndex(str(self.source_path), self.test_index_id)
        index.load_kmtricks_index()

        registry.set_index(index)  # Use set_index method instead
        self.assertTrue(registry.has_index(self.test_index_id))

    def test_get_index_path(self):
        """Test get_index_path method."""
        registry = KmindexRegistry(str(self.registry_path))
        path = registry.get_index_path(self.test_index_id)
        expected = os.path.join(str(self.registry_path), self.test_index_id)
        self.assertEqual(path, expected)

    def test_is_index_dir(self):
        """Test is_index_dir method."""
        registry = KmindexRegistry(str(self.registry_path))
        # Add the index first so it exists in the registry directory
        index = KmtricksIndex(str(self.source_path), self.test_index_id)
        index.load_kmtricks_index()
        registry.add_index(index)

        self.assertTrue(registry.is_index_dir(self.test_index_id))
        self.assertFalse(registry.is_index_dir("nonexistent_index"))


class TestKmtricksIndexV063Params(TestKmtricksIndexBase):
    """Tests for parameters introduced in v0.6.3."""

    def test_auto_load_enabled_by_default(self):
        """By default the index is loaded from disk on construction."""
        index = KmtricksIndex(str(self.temp_path), self.test_index_id)
        self.assertTrue(index.is_loaded)
        self.assertGreater(index.nb_samples, 0)

    def test_auto_load_disabled(self):
        """With auto_load=False properties stay unloaded until explicitly loaded."""
        index = KmtricksIndex(str(self.temp_path), self.test_index_id, auto_load=False)
        self.assertFalse(index.is_loaded)
        self.assertEqual(index.nb_samples, 0)

        index.load_kmtricks_index()
        self.assertTrue(index.is_loaded)
        self.assertGreater(index.nb_samples, 0)


class TestKmindexRegistryV063Params(TestKmtricksIndexBase):
    """Tests for KmindexRegistry parameters introduced in v0.6.3."""

    def test_auto_create_false_raises_when_missing(self):
        """auto_create=False raises NotAnIndexError when index.json is absent."""
        empty_dir = self.temp_path / "no_json"
        empty_dir.mkdir()
        with self.assertRaises(NotAnIndexError):
            KmindexRegistry(str(empty_dir), auto_create=False)

    def test_auto_create_true_creates_json(self):
        """auto_create=True (default) creates index.json when it is absent."""
        new_dir = self.temp_path / "auto_created"
        new_dir.mkdir()
        registry = KmindexRegistry(str(new_dir), auto_create=True)
        self.assertTrue((new_dir / "index.json").exists())
        self.assertTrue(registry.json_exists)

    def test_remove_index_skip_unregistered(self):
        """Removing an unknown index with skip_unregistered=True returns False."""
        registry = KmindexRegistry(str(self.registry_path))
        result = registry.remove_index("nonexistent_index", skip_unregistered=True)
        self.assertFalse(result)

    def test_remove_index_delete_files(self):
        """remove_index(delete_files=True) removes both the entry and on-disk files."""
        registry = KmindexRegistry(str(self.registry_path))
        index = KmtricksIndex(str(self.source_path), self.test_index_id)
        index.load_kmtricks_index()
        registry.add_index(index)

        index_path = registry.get_index_path(self.test_index_id)
        self.assertTrue(os.path.exists(index_path))

        result = registry.remove_index(self.test_index_id, delete_files=True)
        self.assertTrue(result)
        self.assertFalse(registry.has_index(self.test_index_id))
        self.assertFalse(os.path.exists(os.path.realpath(index_path)))


if __name__ == "__main__":
    unittest.main()
