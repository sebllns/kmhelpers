"""
Index class - Object-oriented layer for kmindex operations.

This module provides an Index class that wraps around kmhelpers.py functionality
to provide a more convenient object-oriented interface for working with kmindex
data structures and their associated properties from index.json files.
"""

import json
import os
import shutil
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List

from pykmhelpers.core.utils import Kmindex, Toolbox


class NotAnIndexError(Exception):
    """Exception raised when an existing index is required and is not found in the current context.

    Attributes:
        message -- explanation of the error
    """

    def __init__(self, index_id):
        self.message = f"Index not found: {index_id}"
        super().__init__(self.message)


class IndexCompressionState(Enum):
    """
    Enum representing the compression state of a kmindex.

    Attributes:
        UNKNOWN: Compression state is unknown or not determined
        UNCOMPRESSED: Index contains only uncompressed matrices
        COMPRESSED: Index contains only compressed matrices
        BOTH: Index contains both compressed and uncompressed matrices
    """

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

    def __init__(
        self,
        parent_dir: str,
        index_id: str,
        compressed_state: IndexCompressionState = IndexCompressionState.UNKNOWN,
        auto_load: bool = True,
    ):
        """
        Initialize a KmtricksIndex object.

        Args:
            parent_dir: Parent directory containing the index
            index_id: The ID of the specific index to work with
            compressed_state: Compression state of the index (default: UNKNOWN)

        Raises:
            NotADirectoryError: If the index directory doesn't exist
        """
        self._parent_dir = Toolbox.get_canonical_path(parent_dir)
        self._index_id = index_id
        self._properties: Dict[str, Any] = {
            "nb_samples": 0,
            "nb_partitions": 0,
            "samples": [],
            "bloom_size": 0,
            "kmer_size": 0,
            "minim_size": 0,
            "sha1": "",
            "kmindex_version": "",
            "kmtricks_version": "",
            "bw": 0,
            "index_size": 0,
        }

        self.compress_state: IndexCompressionState = compressed_state

        if not Kmindex.b_index_exists(self._parent_dir, self._index_id):
            raise NotADirectoryError(
                f"Index directory for '{self._index_id}' not found in {self._parent_dir}"
            )

        self._loaded = False

        if auto_load:
            self.load_kmtricks_index()

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def parent_dir(self) -> str:
        return self._parent_dir

    @property
    def id(self) -> str:
        return self._index_id

    @property
    def dir_path(self) -> str:
        """Get the full path to this index directory."""
        return Kmindex.get_index_path(self._parent_dir, self._index_id)

    @property
    def fof_path(self) -> str:
        """Get the path to the kmtricks.fof file."""
        return Kmindex.get_fof_path(self.dir_path)

    @property
    def kmtricks_options_path(self) -> str:
        """Get the path to the kmtricks options.txt file."""
        return Kmindex.get_options_path(self.dir_path)

    @property
    def permutation_path(self) -> str:
        """Get the path to the permutation.bin file."""
        return self.get_path_inside_index("permutation.bin")

    @property
    def metrics_dir_path(self) -> str:
        """Get the path to the metrics directory."""
        return self.get_path_inside_index("metrics")

    @property
    def matrices_dir_path(self) -> str:
        """Get the path to the matrices directory."""
        return Kmindex.get_matrix_dir(self.dir_path)

    # Index properties from JSON
    @property
    def nb_samples(self) -> int:
        """Number of samples in the index."""
        return self._properties.get("nb_samples", 0)

    @property
    def nb_partitions(self) -> int:
        """Number of partitions in the index."""
        return self._properties.get("nb_partitions", 0)

    @property
    def samples(self) -> List[str]:
        """List of sample names."""
        return self._properties.get("samples", [])

    @property
    def bloom_size(self) -> int:
        """Bloom filter size."""
        return self._properties.get("bloom_size", 0)

    @property
    def kmer_size(self) -> int:
        """K-mer size."""
        return self._properties.get("kmer_size", 0)

    @property
    def minim_size(self) -> int:
        """Minimizer size."""
        return self._properties.get("minim_size", 0)

    @property
    def sha1(self) -> str:
        """SHA1 hash of the index."""
        return self._properties.get("sha1", "")

    @property
    def kmindex_version(self) -> str:
        """Version of kmindex used to create this index."""
        return self._properties.get("kmindex_version", "")

    @property
    def kmtricks_version(self) -> str:
        """Version of kmtricks used to create this index."""
        return self._properties.get("kmtricks_version", "")

    @property
    def bw(self) -> int:
        """Bandwidth parameter."""
        return self._properties.get("bw", 0)

    @property
    def index_size(self) -> int:
        """Size of the index."""
        return self._properties.get("index_size", 0)

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
        """
        Get the full path to a file or directory within this index.

        Args:
            path: Relative path within the index directory

        Returns:
            Canonical path to the file or directory
        """
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
        """
        Get the paths to both compression output files for a partition.

        Args:
            partition: Partition number

        Returns:
            Tuple of (blocks_path, ef_path)
        """
        return Kmindex.get_compressed_files_path(self.dir_path, partition)

    def get_matrix_byte_size(self, partition: int, is_compressed: bool = False) -> int:
        """
        Get the size in bytes of a specific matrix partition.

        Args:
            partition: Partition number
            is_compressed: Whether to check compressed matrix (default: False)

        Returns:
            Size in bytes
        """
        return Kmindex.get_bytes_per_matrix(self.dir_path, partition, is_compressed)

    def get_matrix_element_count(self, partition: int) -> int:
        """
        Get the number of elements in a specific matrix partition.

        Args:
            partition: Partition number

        Returns:
            Total number of elements (rows × samples)
        """
        return self.get_matrix_row_count(partition) * self.nb_samples

    def get_matrix_row_count(self, partition: int) -> int:
        """
        Get the number of rows (k-mers) in a specific matrix partition.

        Args:
            partition: Partition number

        Returns:
            Number of rows in the partition
        """
        matrix_size = self.get_matrix_byte_size(partition)
        return Kmindex.get_row_count(matrix_size, self.bytes_per_row, self.header_size)

    def get_matrix_size(self) -> tuple[int, int]:
        """
        Get the dimensions of each matrix partition.

        Returns:
            Tuple of (rows_per_partition, columns) where columns = nb_samples
        """
        return self.bloom_size // self.nb_partitions, self.nb_samples

    def check_structure(self) -> bool:
        """
        Check if the index has the expected file structure and properties.

        Returns:
            bool: True if structure is valid, False otherwise
        """
        ok = True

        if self.bloom_size <= 0:
            print("Bloom size cannot be null")
            ok = False

        if self.nb_samples <= 0:
            print("Number of samples cannot be null")
            ok = False

        if self.nb_partitions <= 0:
            print("Number of partitions cannot be null")
            ok = False

        if self.kmer_size <= 0:
            print("K-mer size cannot be null")
            ok = False

        if self.minim_size <= 0:
            print("Minimizer size cannot be null")
            ok = False

        if len(self.samples) == 0:
            print("Samples list cannot be empty")
            ok = False

        if len(self.samples) != self.nb_samples:
            print("Samples list length must match nb_samples")
            ok = False

        if not Kmindex.check_index_structure(self.dir_path, self.nb_partitions):
            ok = False

        ref_size = self.get_matrix_byte_size(
            0, self.compress_state == IndexCompressionState.COMPRESSED
        )

        for p in range(self.nb_partitions):
            size = self.get_matrix_byte_size(
                p, self.compress_state == IndexCompressionState.COMPRESSED
            )
            if size != ref_size:
                print(
                    f"Partition {p} size ({size} bytes) does not match reference partition size ({ref_size} bytes)"
                )
                ok = False

        if not ok:
            print(f"[Warning] Index {self._index_id} has incorrect structure")

        return ok

    def set_property(self, key: str, value: Any) -> bool:
        """
        Set a property value in the index metadata.

        Args:
            key: Property key to set
            value: Value to assign

        Returns:
            True if successful, False otherwise
        """
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
        """
        Import properties from a dictionary into the index metadata.

        Args:
            props: Dictionary of properties to import
        """
        try:
            self._properties.update(props)
        except TypeError as e:
            print(f"An error occurred: {e}")

    def load_kmtricks_index(self, force: bool = False) -> None:
        """
        Load index properties from kmtricks files (options.txt and kmtricks.fof).

        This method reads the options.txt and kmtricks.fof files and populates
        the index properties accordingly.

        Raises:
            FileNotFoundError: If required files (options.txt or kmtricks.fof) are not found
        """

        if self._loaded and not force:
            return

        # Check required files exist
        options_path = Kmindex.get_options_path(self.dir_path)
        if not os.path.exists(options_path):
            raise FileNotFoundError(f"Options file not found: {options_path}")

        fof_path = Kmindex.get_fof_path(self.dir_path)
        if not os.path.exists(fof_path):
            raise FileNotFoundError(f"FOF file not found: {fof_path}")

        self.import_properties(Kmindex.load_options_file(options_path))
        # load samples
        samples = Kmindex.load_fof_file(fof_path)
        self._properties["samples"] = samples
        self._properties["nb_samples"] = len(samples)
        self._loaded = True

    def destroy_entire_index(self) -> bool:
        # Destroy the entire index with its content
        try:
            import shutil

            print(f"Destroying index: {self._index_id}")
            shutil.rmtree(self.dir_path, onexc=lambda _f, p, _e: print(f"Error: {p}"))
            self._parent_dir = ""
            return True
        except Exception as e:
            print(f"Error removing index: {e}")
            return False

    def copy_to(self, destination: str) -> bool:
        """
        Copy this index to a destination directory.

        Args:
            destination: Destination directory path where the index will be copied

        Returns:
            True if copy was successful, False otherwise
        """
        try:
            import shutil

            destination = Toolbox.get_canonical_path(destination)

            # Create destination parent directory if it doesn't exist
            os.makedirs(destination, exist_ok=True)

            # Get source and destination paths
            source_path = self.dir_path
            dest_path = os.path.join(destination, self._index_id)

            # Check if source exists
            if not os.path.exists(source_path):
                print(f"Error: Source index directory does not exist: {source_path}")
                return False

            # Check if destination already exists
            if os.path.exists(dest_path):
                print(f"Error: Destination already exists: {dest_path}")
                return False

            # Copy the entire index directory
            shutil.copytree(source_path, dest_path)

            print(f"Successfully copied index '{self._index_id}' to {destination}")

            return True

        except Exception as e:
            print(f"Error copying index: {e}")
            return False

    def move_to(self, destination: str) -> bool:
        """
        Move this index to a destination directory.

        Args:
            destination: Destination directory path where the index will be moved

        Returns:
            True if move was successful, False otherwise
        """
        try:
            destination = Toolbox.get_canonical_path(destination)
            self.copy_to(destination)

            # Remove old index
            self.destroy_entire_index()

            # Update the _parent_dir property to reflect the new location
            self._parent_dir = destination

            print(f"Successfully moved index '{self._index_id}' to {destination}")
            return True

        except Exception as e:
            print(f"Error moving index: {e}")
            return False

    def rename(self, new_id) -> bool:
        """
        Rename this index to a new ID.

        Args:
            new_id: New index ID

        Returns:
            True if rename was successful, False otherwise
        """
        try:
            # Validate new_id
            if not new_id or not isinstance(new_id, str):
                print(f"Error: Invalid new index ID: {new_id}")
                return False

            if new_id == self._index_id:
                print(f"Error: New ID is the same as current ID: {new_id}")
                return False

            # Get current and new paths
            old_path = self.dir_path
            new_path = Kmindex.get_index_path(self._parent_dir, new_id)

            # Check if new path already exists
            if os.path.exists(new_path):
                print(f"Error: Index with ID '{new_id}' already exists at {new_path}")
                return False

            # Rename the directory
            os.rename(old_path, new_path)

            # Update the index ID
            self._index_id = new_id

            print(f"Successfully renamed index to '{new_id}'")
            return True

        except Exception as e:
            print(f"Error renaming index: {e}")
            return False

    def __str__(self) -> str:
        """String representation of the index."""
        return f"Index(id='{self._index_id}', _parent_dir='{self._parent_dir}', nb_samples={self.nb_samples}, bloom_size={self.bloom_size}, nb_partitions={self.nb_partitions})"

    def __repr__(self) -> str:
        """Detailed representation of the index."""
        return f"Index(root_path='{self._parent_dir}', _index_id='{self._index_id}')"

    def __iter__(self):
        """Iterate over all samples."""
        for i in self.samples:
            yield i


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
        self._root_path = Toolbox.get_canonical_path(root_path)

        if not self.json_exists:
            Kmindex.create_empty_index_json(self._root_path)

        self._standby = False
        self.load_json()

    @property
    def root_path(self) -> str:
        return self._root_path

    @property
    def json_path(self) -> str:
        """Get path to the index.json file."""
        return Kmindex.get_json_path(self._root_path)

    @property
    def json_exists(self) -> bool:
        return Kmindex.b_json_exists(self._root_path)

    def load_json(self) -> None:
        """Load the index.json file into memory."""
        # Load the JSON data
        if not self._standby:
            with open(self.json_path, "r") as f:
                self._json_data = json.load(f)

    def _backup_json(self) -> None:
        """Create a backup of the index.json file with .bak extension."""
        backup_path = f"{self.json_path}.bak"
        shutil.copy2(self.json_path, backup_path)

    def list_indices(self) -> List[str]:
        """
        Get list of all available index IDs.

        Returns:
            List[str]: List of index IDs
        """
        return list(self._json_data["index"].keys())

    def get_index_properties(self, _index_id: str) -> Dict[str, Any]:
        """
        Get the properties dictionary for a specific index.

        Args:
            _index_id: The index ID to retrieve properties for

        Returns:
            Dictionary containing all properties for the index
        """
        return self._json_data["index"][_index_id]

    def get_index_path(self, _index_id: str) -> str:
        return os.path.join(self._root_path, _index_id)

    def is_index_dir(self, _index_id: str) -> bool:
        return os.path.isdir(self.get_index_path(_index_id))

    def get_all(self) -> List[KmtricksIndex]:
        items = []
        for i in self:
            items.append(i)
        return items

    def get_index(self, _index_id: str) -> KmtricksIndex:
        """
        Get an Index object for a specific index ID.

        Args:
            _index_id (str): The index ID to retrieve

        Returns:
            Index: Index object for the specified ID

        Raises:
            KeyError: If _index_id doesn't exist
        """

        if not self.has_index(_index_id):
            raise KeyError(
                f"Index ID '{_index_id}' not found. Available IDs: {self.list_indices()}"
            )

        # Create empty Index instance and load properties from JSON
        index = KmtricksIndex(self._root_path, _index_id, auto_load=False)
        index.import_properties(self.get_index_properties(_index_id))
        index.set_property("kmer_size", index.get_property("smer_size"))

        return index

    def has_index(self, _index_id: str) -> bool:
        """
        Check if an index ID exists.

        Args:
            _index_id (str): Index ID to check

        Returns:
            bool: True if index exists
        """
        return _index_id in self._json_data["index"]

    def add_index(self, index: KmtricksIndex) -> bool:
        """
        Add a new index to the registry.

        Args:
            index: KmtricksIndex object to add

        Returns:
            True if index was added, False if it already exists
        """
        if self.has_index(index._index_id):
            return False
        Kmindex.register_index_in_json(
            index._parent_dir, self._root_path, index._index_id
        )
        # Reload json after kmindex modified it
        self.load_json()
        return True

    def remove_index(self, index_id: str, delete_files: bool = False) -> bool:
        """
        Remove an index from the registry.

        Args:
            _index_id: The index ID to remove from the registry

        Returns:
            True if index was removed, False if it doesn't exist
        """
        if not self.has_index(index_id):
            return False

        index_path = self.get_index_path(index_id)

        # Delete files if requested
        if delete_files:
            try:
                # Get index before removal (needed to delete files)
                shutil.rmtree(
                    os.path.realpath(index_path),
                    ignore_errors=True,
                )
                print(f"✓ Deleted index files from disk")
            except Exception as e:
                print(f"⚠ Failed to delete some files: {e}")

        try:
            if os.path.islink(index_path):
                os.unlink(index_path)
        except Exception as e:
            print(f"Error deleting link {index_path}: {e}")

        # Remove the index from the JSON data
        del self._json_data["index"][index_id]

        # Create backup before writing
        self._backup_json()

        # Write the updated JSON back to file
        with open(self.json_path, "w") as f:
            json.dump(self._json_data, f, indent=4)

        return True

    def set_index(self, index: KmtricksIndex) -> None:
        self._standby = True
        if self.has_index(index._index_id):
            self.remove_index(index._index_id)
        assert self.add_index(index), f"Could not add index {index}"
        self._standby = False
        self.load_json()

    def relink(self, index_id: str | None, path: str):
        if not os.path.isdir(path):
            raise NotADirectoryError(path)

        if index_id:
            if not self.has_index(index_id):
                raise NotAnIndexError(index_id)
            ids = [index_id]
        else:
            ids = self.list_indices()

        for i in ids:
            index_link = self.get_index_path(i)
            index_path = os.path.join(path, i)
            try:
                if os.path.isdir(index_path):
                    KmtricksIndex(path, i)
                    if os.path.islink(index_link):
                        os.unlink(index_link)
                    os.symlink(index_path, index_link, target_is_directory=True)
            except Exception as e:
                print(f"Error linking {i}: {e}")

    def rename_index(self, old_index_id: str, new_index_id: str) -> bool:
        """
        Rename an index in the registry.

        Args:
            old_index_id: The current index ID
            new_index_id: The new index ID

        Returns:
            True if index was renamed, False if operation failed
        """
        # Check if old index exists
        if not self.has_index(old_index_id):
            return False

        # Check if new index ID already exists
        if self.has_index(new_index_id):
            return False

        # Create backup before writing
        self._backup_json()

        idx = self.get_index(old_index_id)

        self.remove_index(old_index_id, delete_files=False)
        idx.rename(new_index_id)
        self.add_index(idx)

        # Write the updated JSON back to file
        with open(self.json_path, "w") as f:
            json.dump(self._json_data, f, indent=4)

        return True

    def import_directory(self, path):
        print(f"Import indexes from {path}:")
        count = 0
        for f in Path(path).iterdir():
            if f.is_dir():
                try:
                    if self.add_index(KmtricksIndex(path, f.name)):
                        count += 1
                        print(f" - {f.name}")
                except:
                    pass

    def check_dirs(self) -> None:
        assert (
            self._json_data["path"] == self._root_path
        ), "Index root paths do not match"
        indices = self.list_indices()
        for i in indices:
            assert self.is_index_dir(i), f"Index not found: {i}"

    def compress(
        self,
        index_name: str,
        block_size: int = 8,
        sampling: int = 20000,
        column_per_block: int = 0,
        cpr_level: int = 3,
        threads: int = 14,
        reorder: bool = False,
        delete_uncompressed: bool = False,
        check_results: bool = False,
        verbose: str = "info",
    ) -> dict:
        """
        Compress an index using kmindex compress command.

        This method is a convenience wrapper that uses KmindexWrapper to compress
        an index registered in this registry.

        Args:
            index_name: Name of the index to compress (must exist in registry).
            block_size: Size of uncompressed blocks in MB (default: 8).
            sampling: Number of rows to sample for reordering (default: 20000).
            column_per_block: Reorder columns by group of N (0=all columns together).
                             Must be a multiple of 8 (default: 0).
            cpr_level: Compression level in range [1-22] (default: 3).
            threads: Number of threads to use (default: 14).
            reorder: Whether to reorder columns before compressing (default: False).
            delete_uncompressed: Delete uncompressed index after successful compression (default: False).
            check_results: Check query results after compressing (default: False).
            verbose: Verbosity level (debug|info|warning|error) (default: info).

        Returns:
            Dictionary containing compression results from KmindexWrapper.

        Raises:
            ValueError: If index_name not found in registry.
            subprocess.CalledProcessError: If kmindex compress command fails.

        Example:
            >>> registry = KmindexRegistry("/path/to/registry")
            >>> result = registry.compress(
            ...     index_name="my_index",
            ...     reorder=True,
            ...     block_size=8,
            ...     threads=8
            ... )
        """
        # Validate index exists in registry
        if not self.has_index(index_name):
            raise ValueError(
                f"Index '{index_name}' not found in registry. "
                f"Available indices: {self.list_indices()}"
            )

        # Import here to avoid circular imports
        from pykmhelpers.core.kmindex_wrapper import KmindexWrapper

        # Use KmindexWrapper to compress the index
        wrapper = KmindexWrapper()
        result = wrapper.compress(
            input_registry=self._root_path,
            index_name=index_name,
            block_size=block_size,
            sampling=sampling,
            column_per_block=column_per_block,
            cpr_level=cpr_level,
            threads=threads,
            reorder=reorder,
            delete_uncompressed=delete_uncompressed,
            check_results=check_results,
        )

        return result

    def __iter__(self):
        """Iterate over all Index objects."""
        for _index_id in self.list_indices():
            yield self.get_index(_index_id)

    def __len__(self) -> int:
        """Get number of indices."""
        return len(self._json_data["index"])

    def __str__(self) -> str:
        """String representation."""
        indices = self.list_indices()
        return f"IndexRegistry(path='{self._root_path}', indices={len(indices)}: {indices})"

    def __getitem__(self, _index_id: str) -> KmtricksIndex | None:
        if self.has_index(_index_id):
            return self.get_index(_index_id)
        return None

    def __setitem__(self, index: KmtricksIndex) -> None:
        self.set_index(index)
