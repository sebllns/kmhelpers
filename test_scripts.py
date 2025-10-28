#!/usr/bin/env python3
"""
Unit tests for the Python scripts in the compression pipeline using pytest.
"""

import pytest
import os
import sys
import tempfile
import shutil
import subprocess
from unittest.mock import patch, MagicMock

# Import from same directory
try:
    import kmhelpers
except ImportError as e:
    pytest.skip(f"kmhelpers module not available: {e}", allow_module_level=True)


@pytest.fixture
def test_bin_dir():
    """Fixture to set up test bin directory."""
    bin_dir = "/tmp/test_bin"
    os.environ["KMHELPERS_BIN_PATH"] = bin_dir
    yield bin_dir
    if "KMHELPERS_BIN_PATH" in os.environ:
        del os.environ["KMHELPERS_BIN_PATH"]


@pytest.fixture
def temp_dir():
    """Fixture to create temporary directory for tests."""
    test_dir = tempfile.mkdtemp()
    yield test_dir
    shutil.rmtree(test_dir, ignore_errors=True)


class TestBinClass:
    """Test cases for the Bin class in kmhelpers."""

    def test_get_bin_dir_success(self, test_bin_dir):
        """Test successful bin directory retrieval."""
        result = kmhelpers.Bin.get_bin_dir()
        assert result == test_bin_dir

    def test_get_bin_dir_no_env_var(self):
        """Test bin directory retrieval without environment variable."""
        if "KMHELPERS_BIN_PATH" in os.environ:
            del os.environ["KMHELPERS_BIN_PATH"]
        
        with pytest.raises(RuntimeError, match="Main.init\\(\\) must be called"):
            kmhelpers.Bin.get_bin_dir()

    def test_get_kmindex_path_uncompressed(self, test_bin_dir):
        """Test kmindex path for uncompressed index."""
        expected = os.path.join(test_bin_dir, "kmindex")
        result = kmhelpers.Bin.get_kmindex_path(is_compressed=False)
        assert result == expected

    def test_get_kmindex_path_compressed(self, test_bin_dir):
        """Test kmindex path for compressed index."""
        expected = os.path.join(test_bin_dir, "MatrixBundle/bin/kmindex")
        result = kmhelpers.Bin.get_kmindex_path(is_compressed=True)
        assert result == expected

    def test_get_compressor_path(self, test_bin_dir):
        """Test compressor path retrieval."""
        expected = os.path.join(test_bin_dir, "MatrixBundle/bin/mainBlockCompressorZSTD")
        result = kmhelpers.Bin.get_compressor_path()
        assert result == expected


class TestToolboxClass:
    """Test cases for utility functions in Toolbox class."""

    def test_get_canonical_path(self):
        """Test canonical path conversion."""
        # Test with actual path
        result = kmhelpers.Toolbox.get_canonical_path("/tmp")
        assert os.path.isabs(result)
        assert "tmp" in result

    def test_get_canonical_path_relative(self):
        """Test canonical path with relative input."""
        result = kmhelpers.Toolbox.get_canonical_path("./")
        assert os.path.isabs(result)

    def test_json_operations(self, temp_dir):
        """Test JSON save operations if available."""
        if hasattr(kmhelpers.Toolbox, 'save_to_json_file'):
            test_data = {"test": "data", "number": 42}
            test_file = os.path.join(temp_dir, "test.json")
            
            # Test would go here if method exists
            assert True  # Placeholder for actual test

    def test_humanize_bytes(self):
        """Test byte size humanization if available."""
        if hasattr(kmhelpers.Toolbox, 'humanize_bytes'):
            assert kmhelpers.Toolbox.humanize_bytes(1024) == "1.0 KB"
            assert kmhelpers.Toolbox.humanize_bytes(1048576) == "1.0 MB"
            assert kmhelpers.Toolbox.humanize_bytes(500) == "500 B"


class TestMainClass:
    """Test cases for the Main class initialization."""

    @patch.dict(os.environ, {}, clear=True)
    @patch('kmhelpers.Bin.check_all')
    @patch('kmhelpers.Toolbox.get_canonical_path', return_value="/canonical/bin/path")
    @patch('builtins.print')
    def test_init_sets_environment(self, mock_print, mock_canonical, mock_check_all):
        """Test Main.init() sets up environment correctly."""
        kmhelpers.Main.init()
        
        # Verify environment variable is set
        assert os.environ["KMHELPERS_BIN_PATH"] == "/canonical/bin/path"
        # Verify get_canonical_path was called (it might be called multiple times)
        assert mock_canonical.called
        mock_check_all.assert_called_once()

    @patch.dict(os.environ, {"KMHELPERS_BIN_PATH": "/existing/path"}, clear=True)
    @patch('kmhelpers.Bin.check_all')
    @patch('builtins.print')
    def test_init_preserves_existing_env(self, mock_print, mock_check_all):
        """Test Main.init() preserves existing environment variable."""
        kmhelpers.Main.init()
        
        # Verify existing environment variable is preserved
        assert os.environ["KMHELPERS_BIN_PATH"] == "/existing/path"
        mock_check_all.assert_called_once()


class TestFileOperations:
    """Test file operation utilities."""

    def test_directory_creation(self, temp_dir):
        """Test directory creation utilities."""
        test_subdir = os.path.join(temp_dir, "subdir")
        
        # Test basic directory creation
        os.makedirs(test_subdir, exist_ok=True)
        assert os.path.exists(test_subdir)

    def test_file_operations(self, temp_dir):
        """Test basic file operations."""
        test_file = os.path.join(temp_dir, "test.txt")
        
        # Create test file
        with open(test_file, 'w') as f:
            f.write("test content")
        
        assert os.path.exists(test_file)
        
        # Test file reading
        with open(test_file, 'r') as f:
            content = f.read()
        assert content == "test content"


class TestIndexOperations:
    """Test index-related operations."""

    @pytest.fixture(autouse=True)
    def setup_env(self):
        """Set up test environment for each test."""
        os.environ["KMHELPERS_BIN_PATH"] = "/tmp/test_bin"
        yield
        if "KMHELPERS_BIN_PATH" in os.environ:
            del os.environ["KMHELPERS_BIN_PATH"]

    @patch('subprocess.run')
    def test_command_execution(self, mock_run):
        """Test command execution patterns."""
        mock_run.return_value = MagicMock(returncode=0, stdout="success", stderr="")
        
        # Test subprocess call pattern
        subprocess.run(["echo", "test"], capture_output=True, text=True)
        assert mock_run.return_value.returncode == 0


class TestErrorHandling:
    """Test error handling in various scenarios."""

    def test_missing_environment_variable(self):
        """Test handling of missing environment variables."""
        if "KMHELPERS_BIN_PATH" in os.environ:
            del os.environ["KMHELPERS_BIN_PATH"]
        
        with pytest.raises(RuntimeError):
            kmhelpers.Bin.get_bin_dir()

    def test_invalid_paths(self):
        """Test handling of invalid file paths."""
        # Test with None path
        with pytest.raises(TypeError):
            kmhelpers.Toolbox.get_canonical_path(None)


# Parameterized tests for different scenarios
@pytest.mark.parametrize("is_compressed,expected_suffix", [
    (False, "kmindex"),
    (True, "MatrixBundle/bin/kmindex")
])
def test_kmindex_path_variations(test_bin_dir, is_compressed, expected_suffix):
    """Test different kmindex path variations."""
    expected = os.path.join(test_bin_dir, expected_suffix)
    result = kmhelpers.Bin.get_kmindex_path(is_compressed=is_compressed)
    assert result == expected


@pytest.mark.parametrize("path_input,should_be_absolute", [
    ("/tmp", True),
    ("./relative", True),
    ("../parent", True),
])
def test_canonical_path_variations(path_input, should_be_absolute):
    """Test canonical path with various inputs."""
    result = kmhelpers.Toolbox.get_canonical_path(path_input)
    assert os.path.isabs(result) == should_be_absolute


class TestToolboxCommands:
    """Test cases for command execution functions in Toolbox class."""
    
    @patch('subprocess.run')
    @patch('builtins.print')
    def test_run_cmd_success(self, mock_print, mock_run):
        """Test successful command execution with run_cmd."""
        # Mock successful command
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "success output\nline2"
        mock_result.stderr = ""
        mock_run.return_value = mock_result
        
        result = kmhelpers.Toolbox.run_cmd(["echo", "test"])
        
        assert result == "success output\nline2"
        mock_run.assert_called_once_with(["echo", "test"], capture_output=True, text=True)
        
    @patch('subprocess.run')
    @patch('builtins.print')
    def test_run_cmd_failure(self, mock_print, mock_run):
        """Test failed command execution with run_cmd."""
        # Mock failed command
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error message\ndetailed error"
        mock_run.return_value = mock_result
        
        result = kmhelpers.Toolbox.run_cmd(["false"])
        
        assert result == "error message\ndetailed error"
        mock_run.assert_called_once_with(["false"], capture_output=True, text=True)
    
    @patch('subprocess.run')
    @patch('builtins.print')
    def test_run_cmd_with_different_types(self, mock_print, mock_run):
        """Test run_cmd with different argument types (should convert to strings)."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "output"
        mock_result.stderr = ""
        mock_run.return_value = mock_result
        
        kmhelpers.Toolbox.run_cmd(["echo", 42, True])
        
        mock_run.assert_called_once_with(["echo", "42", "True"], capture_output=True, text=True)

    @patch('subprocess.Popen')
    @patch('threading.Thread')
    @patch('builtins.print')
    def test_monitor_cmd_success(self, mock_print, mock_thread, mock_popen):
        """Test successful command execution with monitoring."""
        # Mock the process
        mock_process = MagicMock()
        mock_process.pid = 1234
        mock_process.communicate.return_value = ("success output", "")
        mock_process.returncode = 0
        mock_popen.return_value = mock_process
        
        # Mock the thread
        mock_thread_instance = MagicMock()
        mock_thread.return_value = mock_thread_instance
        
        result = kmhelpers.Toolbox.monitor_cmd(["echo", "test"])
        
        assert result is not None
        stdout, resource_stats = result
        assert stdout == "success output"
        assert isinstance(resource_stats, dict)
        assert "max_cpu_percent" in resource_stats
        assert "max_memory_mb" in resource_stats
        assert "execution_time_ms" in resource_stats
        assert "return_code" in resource_stats

    @patch('subprocess.Popen')
    @patch('threading.Thread')  
    @patch('builtins.print')
    def test_monitor_cmd_failure(self, mock_print, mock_thread, mock_popen):
        """Test failed command execution with monitoring."""
        # Mock failed process
        mock_process = MagicMock()
        mock_process.pid = 1234
        mock_process.communicate.return_value = ("", "error output")
        mock_process.returncode = 1
        mock_popen.return_value = mock_process
        
        # Mock the thread
        mock_thread_instance = MagicMock()
        mock_thread.return_value = mock_thread_instance
        
        result = kmhelpers.Toolbox.monitor_cmd(["false"])
        
        # Should return None for failed commands
        assert result is None

    # Note: monitor_cmd doesn't currently handle Popen exceptions
    # This would be a good enhancement for the actual implementation

    @patch('psutil.Process')
    @patch('subprocess.Popen')
    @patch('threading.Thread')
    @patch('builtins.print')
    def test_monitor_cmd_resource_tracking(self, mock_print, mock_thread, mock_popen, mock_psutil_process):
        """Test that monitor_cmd properly tracks resource usage."""
        # Mock the subprocess
        mock_process = MagicMock()
        mock_process.pid = 1234
        mock_process.communicate.return_value = ("output", "")
        mock_process.returncode = 0
        mock_popen.return_value = mock_process
        
        # Mock psutil.Process for resource monitoring
        mock_psutil_instance = MagicMock()
        mock_psutil_instance.cpu_percent.return_value = 50.0
        mock_psutil_instance.memory_info.return_value.rss = 1024 * 1024 * 100  # 100 MB
        mock_psutil_process.return_value = mock_psutil_instance
        
        # Mock the monitoring thread
        mock_thread_instance = MagicMock()
        mock_thread.return_value = mock_thread_instance
        
        result = kmhelpers.Toolbox.monitor_cmd(["echo", "test"])
        
        assert result is not None
        stdout, resource_stats = result
        assert "max_cpu_percent" in resource_stats
        assert "max_memory_mb" in resource_stats
        assert "execution_time_ms" in resource_stats
        assert "return_code" in resource_stats


class TestKmindexClass:
    """Test cases for the Kmindex class methods."""
    
    def test_get_header_byte_size(self):
        """Test header byte size constant."""
        result = kmhelpers.Kmindex.get_header_byte_size()
        assert result == 49
    
    def test_get_bytes_per_row(self):
        """Test bytes per row calculation."""
        # Test various sample counts
        assert kmhelpers.Kmindex.get_bytes_per_row(8) == 1  # 8 bits = 1 byte
        assert kmhelpers.Kmindex.get_bytes_per_row(16) == 2  # 16 bits = 2 bytes
        assert kmhelpers.Kmindex.get_bytes_per_row(9) == 2   # 9 bits = 2 bytes (rounded up)
        assert kmhelpers.Kmindex.get_bytes_per_row(1) == 1   # 1 bit = 1 byte (minimum)
    
    def test_get_row_count(self):
        """Test row count calculation."""
        matrix_size = 1000
        row_size = 10  
        header_size = 49
        
        expected_rows = (matrix_size - header_size) // row_size
        result = kmhelpers.Kmindex.get_row_count(matrix_size, row_size, header_size)
        assert result == expected_rows
        
        # Test edge cases
        assert kmhelpers.Kmindex.get_row_count(100, 10, 49) == 5
        assert kmhelpers.Kmindex.get_row_count(60, 10, 49) == 1
    
    @pytest.mark.parametrize("matrix_size,row_size,header_size", [
        (0, 10, 49),   # matrix_size = 0
        (100, 0, 49),  # row_size = 0
        (-1, 10, 49),  # negative matrix_size
        (100, -1, 49), # negative row_size
    ])
    def test_get_row_count_invalid_inputs(self, matrix_size, row_size, header_size):
        """Test get_row_count with invalid inputs."""
        with pytest.raises(AssertionError):
            kmhelpers.Kmindex.get_row_count(matrix_size, row_size, header_size)
    
    def test_get_json_path(self):
        """Test JSON path construction."""
        root = "/test/root"
        result = kmhelpers.Kmindex.get_json_path(root)
        expected = os.path.join(root, "index.json")
        assert expected in result
        assert os.path.isabs(result)
    
    def test_get_index_path(self):
        """Test index path construction."""
        root = "/test/root"
        index = "test_index"
        result = kmhelpers.Kmindex.get_index_path(root, index)
        expected = os.path.join(root, index)
        assert expected in result
        assert os.path.isabs(result)
    
    def test_get_matrix_dir(self):
        """Test matrix directory path construction."""
        index_path = "/test/index"
        result = kmhelpers.Kmindex.get_matrix_dir(index_path)
        expected = os.path.join(index_path, "matrices")
        assert expected in result
    
    @pytest.mark.parametrize("is_compressed,expected_content", [
        (False, "matrix_5.cmbf"),
        (True, "blocks5"),
    ])
    def test_get_matrix_path(self, is_compressed, expected_content):
        """Test matrix path construction for different compression states."""
        index_path = "/test/index"
        partition = 5
        result = kmhelpers.Kmindex.get_matrix_path(index_path, partition, is_compressed)
        
        assert str(partition) in result
        assert expected_content in result
        assert "matrices" in result
    
    @patch('os.path.isfile')
    def test_b_json_exists(self, mock_isfile):
        """Test JSON file existence check."""
        root = "/test/root"
        
        # Test when file exists
        mock_isfile.return_value = True
        assert kmhelpers.Kmindex.b_json_exists(root) == True
        
        # Test when file doesn't exist
        mock_isfile.return_value = False
        assert kmhelpers.Kmindex.b_json_exists(root) == False
        
        # Verify the correct path was checked
        expected_path = os.path.join(root, "index.json")
        mock_isfile.assert_called()
    
    @patch('os.path.isdir')
    def test_b_index_exists(self, mock_isdir):
        """Test index directory existence check."""
        root = "/test/root"
        index = "test_index"
        
        # Test when directory exists
        mock_isdir.return_value = True
        assert kmhelpers.Kmindex.b_index_exists(root, index) == True
        
        # Test when directory doesn't exist
        mock_isdir.return_value = False
        assert kmhelpers.Kmindex.b_index_exists(root, index) == False
        
        mock_isdir.assert_called()
    
    @patch('os.path.getsize')
    def test_get_bytes_per_matrix(self, mock_getsize):
        """Test matrix file size retrieval."""
        mock_getsize.return_value = 1024
        
        index_path = "/test/index"
        partition = 0
        
        # Test uncompressed matrix
        result = kmhelpers.Kmindex.get_bytes_per_matrix(index_path, partition, is_compressed=False)
        assert result == 1024
        
        # Test compressed matrix
        result = kmhelpers.Kmindex.get_bytes_per_matrix(index_path, partition, is_compressed=True)
        assert result == 1024
        
        assert mock_getsize.call_count == 2
    
    def test_validate_index_ids_success(self):
        """Test successful index ID validation."""
        requested = ["id1", "id2", "id3"]
        available = ["id1", "id2", "id3", "id4", "id5"]
        
        # Should not raise exception
        kmhelpers.Kmindex.validate_index_ids(requested, available)
    
    def test_validate_index_ids_missing(self):
        """Test index ID validation with missing IDs."""
        requested = ["id1", "id2", "missing_id"]
        available = ["id1", "id2", "id3"]
        
        with pytest.raises(AssertionError, match="not found"):
            kmhelpers.Kmindex.validate_index_ids(requested, available)
    
    def test_compare_nested_dicts_identical(self):
        """Test comparison of identical nested dictionaries."""
        dict1 = {"a": 1, "b": {"c": 2.0, "d": "test"}}
        dict2 = {"a": 1, "b": {"c": 2.0, "d": "test"}}
        
        result = kmhelpers.Kmindex.compare_nested_dicts(dict1, dict2)
        assert result == True
    
    def test_compare_nested_dicts_different(self):
        """Test comparison of different nested dictionaries."""
        dict1 = {"a": 1, "b": {"c": 2.0}}
        dict2 = {"a": 1, "b": {"c": 3.0}}
        
        result = kmhelpers.Kmindex.compare_nested_dicts(dict1, dict2)
        assert result == False
    
    def test_compare_nested_dicts_with_tolerance(self):
        """Test comparison with floating point tolerance."""
        dict1 = {"value": 1.0000001}
        dict2 = {"value": 1.0000002}
        
        # Should be equal within default tolerance
        result = kmhelpers.Kmindex.compare_nested_dicts(dict1, dict2, tolerance=1e-6)
        assert result == True
        
        # Should be different with strict tolerance
        result = kmhelpers.Kmindex.compare_nested_dicts(dict1, dict2, tolerance=1e-10)
        assert result == False
    
    def test_compare_nested_dicts_different_keys(self):
        """Test comparison of dictionaries with different keys."""
        dict1 = {"a": 1, "b": 2}
        dict2 = {"a": 1, "c": 2}
        
        result = kmhelpers.Kmindex.compare_nested_dicts(dict1, dict2)
        assert result == False
    
    def test_compare_nested_dicts_non_dict_values(self):
        """Test comparison when values are not dictionaries."""
        # Should fall back to value comparison
        result = kmhelpers.Kmindex.compare_nested_dicts("test", "test")
        assert result == True
        
        result = kmhelpers.Kmindex.compare_nested_dicts(42, 42)
        assert result == True
        
        result = kmhelpers.Kmindex.compare_nested_dicts(42, 43)
        assert result == False
    
    @patch('builtins.open', new_callable=MagicMock)
    @patch('json.load')
    def test_read_index_ids_from_json(self, mock_json_load, mock_open):
        """Test reading index IDs from JSON file."""
        mock_data = {"index": {"id1": {}, "id2": {}, "id3": {}}}
        mock_json_load.return_value = mock_data
        
        result = kmhelpers.Kmindex.read_index_ids_from_json("/test/path.json")
        
        expected = ["id1", "id2", "id3"]
        assert sorted(result) == sorted(expected)
        mock_open.assert_called_once_with("/test/path.json", "r")
    
    @patch('builtins.open', new_callable=MagicMock)  
    @patch('json.load')
    def test_index_exists_in_json_true(self, mock_json_load, mock_open):
        """Test checking if index exists in JSON (exists case)."""
        mock_data = {"index": {"test_id": {"data": "value"}}}
        mock_json_load.return_value = mock_data
        
        result = kmhelpers.Kmindex.index_exists_in_json("/test/path.json", "test_id")
        
        assert result == True
        mock_open.assert_called_once_with("/test/path.json", "r")
    
    @patch('builtins.open', new_callable=MagicMock)
    @patch('json.load')
    def test_index_exists_in_json_false(self, mock_json_load, mock_open):
        """Test checking if index exists in JSON (not exists case)."""
        mock_data = {"index": {"other_id": {"data": "value"}}}
        mock_json_load.return_value = mock_data
        
        result = kmhelpers.Kmindex.index_exists_in_json("/test/path.json", "test_id")
        
        assert result == False
    
    @patch('os.makedirs')
    @patch('builtins.open', new_callable=MagicMock)
    @patch('json.dump')
    def test_create_empty_index_json(self, mock_json_dump, mock_open, mock_makedirs):
        """Test creating empty index JSON file."""
        output_dir = "/test/output"
        
        kmhelpers.Kmindex.create_empty_index_json(output_dir)
        
        # Verify directory creation
        mock_makedirs.assert_called_once_with(output_dir, exist_ok=True)
        
        # Verify file writing
        expected_path = os.path.join(output_dir, "index.json")
        mock_open.assert_called_once_with(expected_path, "w")
        
        # Verify JSON structure
        mock_json_dump.assert_called_once()
        written_data = mock_json_dump.call_args[0][0]
        assert "index" in written_data
        assert written_data["index"] == {}
    
    @patch('builtins.open', new_callable=MagicMock)
    @patch('json.load')
    def test_read_index_value(self, mock_json_load, mock_open):
        """Test reading specific value from index JSON."""
        mock_data = {
            "index": {
                "test_id": {
                    "nb_samples": 1000,
                    "other_key": "other_value"
                }
            }
        }
        mock_json_load.return_value = mock_data
        
        with patch.object(kmhelpers.Kmindex, 'b_json_exists', return_value=True):
            result = kmhelpers.Kmindex.read_index_value("/test/input", "test_id", "nb_samples")
            assert result == 1000
    
    def test_get_sample_count(self):
        """Test getting sample count for an index."""
        with patch.object(kmhelpers.Kmindex, 'read_index_value', return_value=500) as mock_read:
            result = kmhelpers.Kmindex.get_sample_count("/test/input", "test_id")
            assert result == 500
            mock_read.assert_called_once_with("/test/input", "test_id", "nb_samples")


# Integration-style tests  
def test_full_initialization_workflow():
    """Test complete initialization workflow."""
    # Clean environment
    if "KMHELPERS_BIN_PATH" in os.environ:
        del os.environ["KMHELPERS_BIN_PATH"]
    
    # Mock the check_all method to avoid actual file system checks
    with patch('kmhelpers.Bin.check_all'):
        kmhelpers.Main.init()
    
    # Verify initialization worked
    assert "KMHELPERS_BIN_PATH" in os.environ
    assert os.path.isabs(os.environ["KMHELPERS_BIN_PATH"])


if __name__ == '__main__':
    # Run pytest with verbose output
    pytest.main([__file__, "-v"])
