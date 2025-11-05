"""
Index class - Object-oriented layer for kmindex operations.

This module provides an Index class that wraps around kmhelpers.py functionality
to provide a more convenient object-oriented interface for working with kmindex
data structures and their associated properties from index.json files.
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from enum import Enum
from kmhelpers.core.utils import Kmindex, Toolbox


class IndexCompressionState(Enum):
    UNKNOWN = 0
    UNCOMPRESSED = 1
    COMPRESSED = 2
    BOTH = 3


class KmtricksIndex:
    """
    Object-oriented wrapper for kmindex operations.

    This class provides a convenient interface to work with kmindex data,
    automatically loading properties from index.json and providing easy
    access to common operations.
    """

    def __init__(self, parent_dir: str, index_id: str):
        """
        Initialize an Index object.

        Args:
            root_path (str): Path to the directory containing index.json
            index_id (str): The ID of the specific index to work with
            properties(Dict[str, Any]): properties loaded from index.json
        Raises:
            NotADirectoryError: If the index directory doesn't exist
        """
        self.parent_dir = Toolbox.get_canonical_path(parent_dir)
        self.index_id = index_id
        self._properties: Dict[str, Any] = {
            "nb_samples": 0,
            "nb_partitions": 0,
            "samples": [],
            "bloom_size": 0,
            "smer_size": 0,
            "minim_size": 0,
            "sha1": "",
            "kmindex_version": "",
            "kmtricks_version": "",
            "bw": 0,
            "index_size": 0,
        }

        self.compress_state: IndexCompressionState = IndexCompressionState.UNKNOWN

        if not Kmindex.b_index_exists(self.parent_dir, self.index_id):
            raise NotADirectoryError(
                f"Index directory for '{self.index_id}' not found in {self.parent_dir}"
            )

    @property
    def dir_path(self) -> str:
        """Get the full path to this index directory."""
        return Kmindex.get_index_path(self.parent_dir, self.index_id)

    @property
    def json_path(self) -> str:
        """Get the path to the index.json file."""
        return Kmindex.get_json_path(self.parent_dir)

    @property
    def fof_path(self):
        return Kmindex.get_fof_path(self.dir_path)

    @property
    def kmtricks_options_path(self):
        return Kmindex.get_options_path(self.dir_path)

    @property
    def permutation_path(self):
        return self.get_path_inside_index("permutation.bin")
    
    @property
    def metrics_dir_path(self):
        return self.get_path_inside_index("metrics")

    @property
    def matrices_dir_path(self) -> str:
        """Get the path to the matrices directory."""
        return Kmindex.get_matrix_dir(self.dir_path)

    # Index properties from JSON
    @property
    def nb_samples(self) -> int:
        """Number of samples in the index."""
        return self._properties["nb_samples"]

    @property
    def nb_partitions(self) -> int:
        """Number of partitions in the index."""
        return self._properties["nb_partitions"]

    @property
    def samples(self) -> List[str]:
        """List of sample names."""
        return self._properties["samples"]

    @property
    def bloom_size(self) -> int:
        """Bloom filter size."""
        return self._properties["bloom_size"]

    @property
    def smer_size(self) -> int:
        """S-mer size."""
        return self._properties["smer_size"]

    @property
    def kmer_size(self) -> int:
        """K-mer size."""
        return self._properties["kmer_size"]

    @property
    def minim_size(self) -> int:
        """Minimizer size."""
        return self._properties["minim_size"]

    @property
    def sha1(self) -> str:
        """SHA1 hash of the index."""
        return self._properties["sha1"]

    @property
    def kmindex_version(self) -> str:
        """Version of kmindex used to create this index."""
        return self._properties["kmindex_version"]

    @property
    def kmtricks_version(self) -> str:
        """Version of kmtricks used to create this index."""
        return self._properties["kmtricks_version"]

    @property
    def bw(self) -> int:
        """Bandwidth parameter."""
        return self._properties["bw"]

    @property
    def index_size(self) -> int:
        """Size of the index."""
        return self._properties["index_size"]

    # Computed properties
    @property
    def bytes_per_row(self) -> int:
        """Number of bytes per row based on sample count."""
        return Kmindex.get_bytes_per_row(self.nb_samples)

    @property
    def header_size(self) -> int:
        """Size of matrix header in bytes."""
        return Kmindex.get_header_byte_size()

    def get_path_inside_index(self, path: str) -> str:
        return Kmindex.get_path_inside_index(self.dir_path, path)
    
    def get_matrix_path(self, partition: int, is_compressed: bool = False) -> str:
        """
        Get the path to a specific matrix partition.

        Args:
            partition (int): Partition number
            is_compressed (bool): Whether to get compressed matrix path

        Returns:
            str: Path to the matrix file
        """
        return Kmindex.get_matrix_path(self.dir_path, partition, is_compressed)

    def get_compressed_files(self, partition: int) -> tuple[str, str]:
        return Kmindex.get_compressed_files_path(self.dir_path, partition)

    def get_matrix_byte_size(self, partition: int, is_compressed: bool = False) -> int:
        """
        Get the size in bytes of a specific matrix partition.

        Args:
            partition (int): Partition number
            is_compressed (bool): Whether to check compressed matrix

        Returns:
            int: Size in bytes
        """
        return Kmindex.get_bytes_per_matrix(self.dir_path, partition, is_compressed)

    def get_matrix_element_count(self, partition: int) -> int:
        """
        Get the number of elements in a specific matrix partition.

        Args:
            partition (int): Partition number

        Returns:
            int: Number of elements
        """
        return self.get_matrix_row_count(partition) * self.nb_samples

    def get_matrix_row_count(self, partition: int) -> int:
        """
        Get the number of rows in a specific matrix partition.

        Args:
            partition (int): Partition number

        Returns:
            int: Number of rows
        """
        matrix_size = self.get_matrix_byte_size(partition)
        return Kmindex.get_row_count(matrix_size, self.bytes_per_row, self.header_size)

    def check_structure(self) -> bool:
        """
        Check if the index has the expected file structure.

        Returns:
            bool: True if structure is valid
        """
        return Kmindex.check_index_structure(self.dir_path, self.nb_partitions)

    def set_property(self, key: str, value: Any) -> bool:
        try:
            self._properties[key] = value
            return True
        except:
            print(f"Error setting property: {key}")
            return False

    def get_property(self, key: str) -> Any:
        """
        Get a specific property from the index metadata.

        Args:
            key (str): Property key

        Returns:
            Any: Property value

        Raises:
            KeyError: If key doesn't exist
        """
        if key not in self._properties:
            raise KeyError(
                f"Property '{key}' not found. Available properties: {list(self._properties.keys())}"
            )
        return self._properties[key]

    def get_all_properties(self) -> Dict[str, Any]:
        """
        Get all properties as a dictionary.

        Returns:
            Dict[str, Any]: All index properties
        """
        return self._properties.copy()

    def import_properties(self, props: Dict[str, Any]) -> None:
        try:
            self._properties.update(props)
        except TypeError as e:
            print(f"An error occurred: {e}")

    def load_kmtricks_index(self):
        # Check required files exist
        options_path = Kmindex.get_options_path(self.dir_path)
        if not os.path.exists(options_path):
            raise FileNotFoundError(f"Options file not found: {options_path}")

        fof_path = Kmindex.get_fof_path(self.dir_path)
        if not os.path.exists(fof_path):
            raise FileNotFoundError(f"FOF file not found: {fof_path}")

        self.import_properties(
            Kmindex.load_options_file(options_path)
        )
        # load samples
        samples = Kmindex.load_fof_file(fof_path)
        self._properties["samples"] = samples
        self._properties["nb_samples"] = len(samples)

    def __str__(self) -> str:
        """String representation of the index."""
        return f"Index(id='{self.index_id}', parent_dir='{self.parent_dir}', nb_samples={self.nb_samples}, bloom_size={self.bloom_size}, nb_partitions={self.nb_partitions})"

    def __repr__(self) -> str:
        """Detailed representation of the index."""
        return f"Index(root_path='{self.parent_dir}', index_id='{self.index_id}')"


class KmindexRegistry:
    """
    Manager class for working with multiple indices in a directory.

    This class provides convenient methods to list, access, and manage
    multiple indices from a single index.json file.
    """

    def __init__(self, root_path: str):
        """
        Initialize an IndexRegistry.

        Args:
            root_path (str): Path to directory containing index.json

        Raises:
            FileNotFoundError: If index.json doesn't exist
        """
        self.root_path = Toolbox.get_canonical_path(root_path)

        if not self.json_exists:
            Kmindex.create_empty_index_json(self.root_path)

        self.load_json()

    @property
    def json_path(self) -> str:
        """Get path to the index.json file."""
        return Kmindex.get_json_path(self.root_path)

    @property
    def json_exists(self) -> bool:
        return Kmindex.b_json_exists(self.root_path)
    
    def load_json(self) -> None:
        # Load the JSON data
        with open(self.json_path, "r") as f:
            self._json_data = json.load(f)

    def list_indices(self) -> List[str]:
        """
        Get list of all available index IDs.

        Returns:
            List[str]: List of index IDs
        """
        return list(self._json_data["index"].keys())

    def get_index_properties(self, index_id: str) -> Dict[str, Any]:
        return self._json_data["index"][index_id]

    def get_index(self, index_id: str) -> KmtricksIndex:
        """
        Get an Index object for a specific index ID.

        Args:
            index_id (str): The index ID to retrieve

        Returns:
            Index: Index object for the specified ID

        Raises:
            KeyError: If index_id doesn't exist
        """

        if not self.has_index(index_id):
            raise KeyError(
                f"Index ID '{index_id}' not found. Available IDs: {self.list_indices()}"
            )

        # Create empty Index instance and load properties from JSON
        index = KmtricksIndex(Toolbox.get_canonical_path(self.root_path), index_id)
        index.import_properties(self.get_index_properties(index_id))

        return index

    def has_index(self, index_id: str) -> bool:
        """
        Check if an index ID exists.

        Args:
            index_id (str): Index ID to check

        Returns:
            bool: True if index exists
        """
        return index_id in self._json_data["index"]

    def add_index(self, index: KmtricksIndex) -> bool:
        if self.has_index(index.index_id):
            return False
        Kmindex.register_index_in_json(index.parent_dir, self.root_path, index.index_id)
        # Reload json after kmindex modified it
        self.load_json()
        return True

    def __iter__(self):
        """Iterate over all Index objects."""
        for index_id in self.list_indices():
            yield self.get_index(index_id)

    def __len__(self) -> int:
        """Get number of indices."""
        return len(self._json_data["index"])

    def __str__(self) -> str:
        """String representation."""
        indices = self.list_indices()
        return (
            f"IndexRegistry(path='{self.root_path}', indices={len(indices)}: {indices})"
        )
