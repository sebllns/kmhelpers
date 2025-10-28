import datetime
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import threading
import subprocess
import psutil
import time
import threading
from typing import Any, Dict, List, Optional, Tuple
from typing import Union
import shutil


class Main:
    ####################################################
    @staticmethod
    def init():
        os.environ.setdefault(
            "KMHELPERS_BIN_PATH", Toolbox.get_canonical_path("./bin/")
        )
        print(f"Bin dir is: {Bin.get_bin_dir()}")
        Bin.check_all()


#########################################################
# Bin class
# Contains methods for binary path management and validation
########################################################
class Bin:
    ####################################################
    @staticmethod
    def get_bin_dir():
        if "KMHELPERS_BIN_PATH" not in os.environ:
            raise RuntimeError(
                "Main.init() must be called at program startup before using get_bin_dir()"
            )
        return Toolbox.get_canonical_path(os.environ["KMHELPERS_BIN_PATH"])

    ####################################################
    @staticmethod
    def get_kmindex_path():
        return os.path.join(Bin.get_bin_dir(), "kmindex")

    ####################################################
    @staticmethod
    def get_compressor_path():
        return os.path.join(Bin.get_bin_dir(), "block_compressor")

    ####################################################
    @staticmethod
    def get_decompressor_path():
        return os.path.join(Bin.get_bin_dir(), "block_decompressor")

    ####################################################
    @staticmethod
    def get_reorderer_path():
        return os.path.join(Bin.get_bin_dir(), "bitmatrix_shuffle")

    ####################################################
    @staticmethod
    def check_all():
        bin_path = Bin.get_bin_dir()
        if not os.path.isdir(bin_path):
            raise NotADirectoryError(f"Binaries directory not found: {bin_path}")

        binaries = [
            Bin.get_kmindex_path(),
            Bin.get_reorderer_path(),
            Bin.get_compressor_path(),
            Bin.get_decompressor_path(),
        ]

        missing_binaries = []
        for binary in binaries:
            binary_path = os.path.join(bin_path, binary)
            if not os.path.isfile(binary_path):
                print(f"Warning: {binary} not found")
            elif not os.access(binary_path, os.X_OK):
                print(f"Warning: {binary} exists but is not executable")

        return missing_binaries


#########################################################
# toolbox class
# Contains utility methods for file and path operations
########################################################
class Toolbox:
    """Utility class for common operations."""

    ####################################################
    @staticmethod
    def save_to_json_file(data, filename, pretty=True):
        """
        Save JSON data directly to a file.

        Args:
            data (str): The JSON data to save
            filename (str): Path where to save the JSON file
            pretty (bool): Whether to format JSON with indentation
        """
        with open(filename, "w") as f:
            if pretty:
                json.dump(data, f, indent=2)
            else:
                json.dump(data, f)

        print(f"JSON data saved to: {filename}")

    ####################################################
    @staticmethod
    def json_diff(file1_path, file2_path):
        """
        Calculate the difference between two JSON files.

        Returns:
            dict: Differences between the two JSON
        """
        with open(file1_path, "r") as f1:
            report1 = json.load(f1)

        with open(file2_path, "r") as f2:
            report2 = json.load(f2)

        differences = {}

        for key in report1.keys():
            if key in report2:
                diff = report2[key] - report1[key]
                differences[key] = diff

        return differences

    ####################################################
    @staticmethod
    def get_canonical_path(path):
        """
        Get the canonical absolute path of a given path.

        Args:
            path (str): The input path to resolve.

        Returns:
            str: The canonical absolute path.
        """
        return os.path.realpath(os.path.expanduser(path))

    ####################################################
    @staticmethod
    def get_basename(path):
        """
        Get the base name of a given path.

        Args:
            path (str): The input path.

        Returns:
            str: The base name of the path.
        """
        return os.path.basename(Toolbox.get_canonical_path(path))

    ####################################################
    @staticmethod
    def get_script_dir():
        return os.path.dirname(os.path.abspath(__file__))

    ####################################################
    @staticmethod
    def read_stream(stream, prefix):
        for line in stream:
            print(f"{prefix}: {line.rstrip()}")

    ####################################################
    @staticmethod
    def get_posix_timestamp():
        """
        Returns the current POSIX timestamp (seconds since Unix epoch)
        """
        return int(time.time())

    ####################################################
    @staticmethod
    def get_human_readable_timestamp():
        """
        Returns the current timestamp in human-readable format
        """
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    ####################################################
    @staticmethod
    def run_cmd(cmd: list):
        """
        Run a command using subprocess and capture its output.
        """

        print("Running command:", *cmd)
        result = subprocess.run(
            [str(arg) for arg in cmd], capture_output=True, text=True
        )

        for line in result.stdout.strip().split("\n"):
            if line:
                print(f"1: {line}")
        for line in result.stderr.strip().split("\n"):
            if line:
                print(f"2: {line}")

        if result.returncode != 0:
            print(f"Error running cmd: {result.returncode}")
            return result.stderr

        return result.stdout

    ####################################################
    @staticmethod
    def monitor_cmd(cmd: list) -> Optional[Tuple[str, dict]]:
        """
        Run a command using subprocess and capture its output along with resource usage.
        Returns: (stdout, resource_stats) or None if error
        """
        print(f"Running command: {' '.join(cmd)}")

        # Resource monitoring variables
        max_cpu = 0.0
        max_memory = 0.0
        monitoring = True

        def monitor_resources(process):
            nonlocal max_cpu, max_memory, monitoring
            try:
                psutil_process = psutil.Process(process.pid)
                while monitoring and process.poll() is None:
                    try:
                        # Get CPU and memory usage
                        cpu_percent = psutil_process.cpu_percent()
                        memory_info = psutil_process.memory_info()
                        memory_mb = memory_info.rss / 1024 / 1024  # Convert to MB

                        # Update maximums
                        max_cpu = max(max_cpu, cpu_percent)
                        max_memory = max(max_memory, memory_mb)

                        time.sleep(0.1)  # Sample every 100ms
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        break
            except Exception as e:
                print(f"Resource monitoring error: {e}")

        # Start the process
        start_time = time.time()
        result = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )

        # Start monitoring in a separate thread
        monitor_thread = threading.Thread(target=monitor_resources, args=(result,))
        monitor_thread.daemon = True
        monitor_thread.start()

        # Wait for completion
        stdout, stderr = result.communicate()
        end_time = time.time()
        monitoring = False

        # Wait for monitoring thread to finish
        monitor_thread.join(timeout=1)

        execution_time = 1000 * (end_time - start_time)

        if result.returncode != 0:
            print(f"Error running cmd: {stderr}")
            return None

        resource_stats = {
            "start_time": start_time,
            "execution_time_ms": round(execution_time, 4),
            "max_cpu_percent": round(max_cpu, 4),
            "max_memory_mb": round(max_memory, 4),
            "return_code": result.returncode,
        }

        print(f"Command completed successfully")
        print(f"Execution time: {resource_stats['execution_time_ms']}ms")
        print(f"Max CPU usage: {resource_stats['max_cpu_percent']}%")
        print(f"Max Memory usage: {resource_stats['max_memory_mb']} MB")
        for line in stdout.strip().split("\n"):
            if line:
                print(f"1: {line}")
        for line in stderr.strip().split("\n"):
            if line:
                print(f"2: {line}")

        return stdout, resource_stats


########################################################
# kmindex class
# Contains methods for handling kmindex operations
########################################################
class Kmindex:
    """Helper class for kmindex operations."""

    ####################################################
    @staticmethod
    def load_options_file(file_path: str) -> Dict[str, Any]:
        """
        Load and parse an options.txt file into a dictionary.

        Args:
            file_path (str): Path to the options.txt file

        Returns:
            Dict[str, Any]: Dictionary containing parsed options with type conversion

        Raises:
            FileNotFoundError: If the file doesn't exist
        """
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"Options file not found: {file_path}")

        with open(file_path, "r") as f:
            content = f.read().strip()

        # Remove "Options: " prefix if present
        if content.startswith("Options: "):
            content = content[9:]

        options = {}
        # Split by comma and parse key=value pairs
        for pair in content.split(", "):
            if "=" in pair:
                key, value = pair.split("=", 1)

                if key == "nb_parts":
                    key = "nb_partitions"

                # Try to convert to appropriate type
                if value.isdigit():
                    options[key] = int(value)
                elif value.replace(".", "", 1).isdigit():
                    options[key] = float(value)
                elif value.lower() in ("true", "false"):
                    options[key] = value.lower() == "true"
                else:
                    options[key] = value

        return options

    ####################################################
    @staticmethod
    def load_fof_file(file_path: str) -> List[str]:
        """
        Load a kmtricks.fof file and extract sample IDs.

        Args:
            file_path (str): Path to the kmtricks.fof file

        Returns:
            List[str]: List of sample IDs

        Raises:
            FileNotFoundError: If the file doesn't exist
        """
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"FOF file not found: {file_path}")

        sample_ids = []
        with open(file_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and ":" in line:
                    sample_id = line.split(":", 1)[0].strip()
                    sample_ids.append(sample_id)

        return sample_ids

    ####################################################
    @staticmethod
    def get_header_byte_size():
        return 49

    ####################################################
    @staticmethod
    def compare_matrices_size(
        folders: List[str], type: List[str], index: str
    ) -> Dict[str, Any]:
        """
        Compare matrix sizes across folders and partitions.
        Args:
            folders: List of folder paths to analyze
            partition_count: Number of partitions to check
        Returns:
            Dictionary containing analysis results with folder sizes and matrix sizes
        """

        partition_count = 0

        for folder in folders:
            p = Kmindex.get_partition_count(folder, index)
            if partition_count == 0:
                partition_count = p
            elif partition_count != p:
                raise RuntimeError(
                    f"Partition count differs between original and {folder}"
                )

        results = {
            "folders": folders,
            "partition_count": partition_count,
            "folder_sizes_bytes": [0] * len(folders),
            "matrix_sizes_bytes": [
                [0 for _ in range(len(folders) + 1)] for _ in range(partition_count)
            ],
        }

        # Calculate matrix sizes for each partition and folder
        for i in range(partition_count):
            for j, folder in enumerate(folders):
                is_compressed = "compressed" in type[j]
                matrix_path = Kmindex.get_matrix_path(
                    Kmindex.get_index_path(folder, index), i, is_compressed
                )
                if os.path.isfile(matrix_path):
                    matrix_size = os.path.getsize(matrix_path)
                else:
                    print(f"ERROR: Matrix file {matrix_path} does not exist.")
                    matrix_size = 0

                if type[j] == "reordered_compressed" or type[j] == "compressed":
                    matrix_size += os.path.getsize(f"{matrix_path}_ef")

                if j == 0:
                    results["matrix_sizes_bytes"][i][j] = matrix_size
                else:
                    results["matrix_sizes_bytes"][i][j] = (
                        round(
                            (matrix_size - results["matrix_sizes_bytes"][i][0])
                            / results["matrix_sizes_bytes"][i][0],
                            4,
                        )
                        if results["matrix_sizes_bytes"][i][0] > 0
                        else 0
                    )

                    if (
                        type[j] == "reordered"
                        and results["matrix_sizes_bytes"][i][j] != 0
                    ):
                        print(
                            f"ERROR: Reordered index {folders[j]} has different size for partition {i} compared to original."
                        )

                results["folder_sizes_bytes"][j] += matrix_size
            results["matrix_sizes_bytes"][i][-1] = i

        for j in range(1, len(folders)):
            results["folder_sizes_bytes"][j] = (
                (results["folder_sizes_bytes"][j] - results["folder_sizes_bytes"][0])
                / results["folder_sizes_bytes"][0]
                if results["folder_sizes_bytes"][0] > 0
                else 0
            )
        return results

    ####################################################
    @staticmethod
    def validate_index_ids(requested_ids: list, available_ids: list) -> None:
        """
        Validate that all requested IDs exist in the available IDs list.

        Raises AssertionError if any requested ID is not found.
        """
        missing_ids = [
            req_id for req_id in requested_ids if req_id not in available_ids
        ]

        if missing_ids:
            raise AssertionError(
                f"Index IDs {missing_ids} not found. " f"Available: {available_ids}"
            )

    ####################################################
    @staticmethod
    def create_empty_index_json(output_dir) -> str:
        """
        Create an empty index.json file in the specified output directory.
        """

        os.makedirs(output_dir, exist_ok=True)

        output_file = Kmindex.get_json_path(output_dir)
        # Check if index.json already exists
        if os.path.exists(output_file):
            return ""

        # Create the JSON structure
        index_data = {
            "index": {},
            "path": os.path.realpath(Toolbox.get_canonical_path(output_dir)),
        }

        # Write the JSON file
        with open(output_file, "w") as f:
            json.dump(index_data, f, indent=4)

        print(f"Created empty index.json at: {output_file}")
        return output_file

    ####################################################
    @staticmethod
    def check_index_structure(directory_path, partition_count=256):
        """
        Check if the given directory contains the expected structure and print missing files.

        Args:
            directory_path (str): Path to the directory to check

        Returns:
            bool: True if all expected files are present, False otherwise
        """

        # Define the expected structure
        expected_files = {"build_infos.txt", "hash.info", "kmtricks.fof", "options.txt"}

        expected_dirs = {"config_gatb", "matrices", "repartition_gatb"}

        expected_config_files = {"config_gatb/gatb.config"}

        expected_repartition_files = {"repartition_gatb/repartition.minimRepart"}

        # Generate expected matrix files (matrix_0.cmbf to matrix_255.cmbf)
        expected_matrix_files = set()
        for i in range(partition_count):
            expected_matrix_files.add(f"matrices/matrix_{i}.cmbf")

        # Combine all expected files/paths
        all_expected = (
            expected_files
            | expected_dirs
            | expected_config_files
            | expected_repartition_files
            | expected_matrix_files
        )

        missing_items = []
        all_present = True

        # Check if directory exists
        if not os.path.exists(directory_path):
            print(f"ERROR: Directory '{directory_path}' does not exist!")
            return False

        print(f"Checking index structure in: {directory_path}")

        # Check each expected item
        for item in sorted(all_expected):
            item_path = os.path.join(directory_path, item)

            if not os.path.exists(item_path):
                missing_items.append(item)
                all_present = False

        # Report results
        if missing_items:
            print(f"MISSING ITEMS ({len(missing_items)}):")
            print("-" * 30)

            # Group missing items by category for better readability
            missing_root_files = [
                item for item in missing_items if "/" not in item and "." in item
            ]
            missing_dirs = [
                item for item in missing_items if "/" not in item and "." not in item
            ]
            missing_config = [
                item for item in missing_items if item.startswith("config_gatb/")
            ]
            missing_matrices = [
                item for item in missing_items if item.startswith("matrices/")
            ]
            missing_repartition = [
                item for item in missing_items if item.startswith("repartition_gatb/")
            ]

            if missing_root_files:
                print("Root files:")
                for item in missing_root_files:
                    print(f"  - {item}")
                print()

            if missing_dirs:
                print("Directories:")
                for item in missing_dirs:
                    print(f"  - {item}/")
                print()

            if missing_config:
                print("Config files:")
                for item in missing_config:
                    print(f"  - {item}")
                print()

            if missing_repartition:
                print("Repartition files:")
                for item in missing_repartition:
                    print(f"  - {item}")
                print()

            if missing_matrices:
                print(f"Matrix files ({len(missing_matrices)}):")
                # Show first few and last few if many are missing
                if len(missing_matrices) > 10:
                    for item in missing_matrices[:5]:
                        print(f"  - {item}")
                    print(f"  ... ({len(missing_matrices) - 10} more)")
                    for item in missing_matrices[-5:]:
                        print(f"  - {item}")
                else:
                    for item in missing_matrices:
                        print(f"  - {item}")
                print()

        return all_present

    ####################################################
    @staticmethod
    def read_index_ids_from_json(json_file_path):
        with open(json_file_path, "r") as file:
            data = json.load(file)
        index_ids = list(data["index"].keys())
        return index_ids

    ####################################################
    @staticmethod
    def index_exists_in_json(json_file_path, index_id):
        with open(json_file_path, "r") as file:
            data = json.load(file)
        return index_id in data["index"]

    ####################################################
    @staticmethod
    def get_row_count(matrix_byte_size, row_byte_size, header_byte_size):
        assert matrix_byte_size > 0
        assert row_byte_size > 0
        assert header_byte_size >= 0
        return (matrix_byte_size - header_byte_size) // row_byte_size

    ####################################################
    @staticmethod
    def get_bytes_per_matrix(index_path, partition, is_compressed=False):
        return os.path.getsize(
            Kmindex.get_matrix_path(index_path, partition, is_compressed)
        )

    ####################################################
    @staticmethod
    def get_bytes_per_row(sample_count):
        return (sample_count + 7) // 8

    ####################################################
    @staticmethod
    def get_partition_count(input_dir, index_id):
        return Kmindex.read_index_value(input_dir, index_id, "nb_partitions")

    ####################################################
    @staticmethod
    def get_sample_count(input_dir, index_id):
        return Kmindex.read_index_value(input_dir, index_id, "nb_samples")

    ####################################################
    @staticmethod
    def read_index_value(input_dir, index_id, key):
        index_json_path = Kmindex.get_json_path(input_dir)
        if not Kmindex.b_json_exists(input_dir):
            raise FileNotFoundError(f"index.json not found in {input_dir}")

        with open(index_json_path, "r") as file:
            data = json.load(file)

        if index_id not in data["index"]:
            raise KeyError(f"Index ID {index_id} not found in index.json")

        if key not in data["index"][index_id]:
            raise KeyError(f"Key {key} not found for index ID {index_id}")

        return data["index"][index_id][key]

    ####################################################

    @staticmethod
    def get_matrix_dir(index_path):
        """
        Constructs the directory path for a matrix based on the index path and partition number.
        """
        return Toolbox.get_canonical_path(os.path.join(index_path, "matrices"))

    ####################################################
    @staticmethod
    def get_matrix_path(index_path, partition, is_compressed=False):
        """
        Constructs the path to a matrix file based on the index path and partition number.
        """
        return os.path.join(
            Kmindex.get_matrix_dir(index_path),
            f"blocks{partition}" if is_compressed else f"matrix_{partition}.cmbf",
        )

    ####################################################
    @staticmethod
    def get_index_path(root, index):
        return Toolbox.get_canonical_path(os.path.join(root, index))

    ####################################################
    @staticmethod
    def get_build_info_path(root):
        return Toolbox.get_canonical_path(os.path.join(root, "build_infos.txt"))

    ####################################################
    @staticmethod
    def get_fof_path(root):
        return Toolbox.get_canonical_path(os.path.join(root, "kmtricks.fof"))

    ####################################################
    @staticmethod
    def get_options_path(root):
        return Toolbox.get_canonical_path(os.path.join(root, "options.txt"))

    ####################################################
    @staticmethod
    def get_json_path(root):
        return Toolbox.get_canonical_path(os.path.join(root, "index.json"))

    ####################################################
    @staticmethod
    def b_json_exists(root):
        return os.path.isfile(Kmindex.get_json_path(root))

    ####################################################
    @staticmethod
    def b_index_exists(root, index):
        return os.path.isdir(Kmindex.get_index_path(root, index))

    ####################################################
    @staticmethod
    def register_index_in_json(input_dir, output_dir, index_id):
        """
        Register a new index in the index.json file located in the output directory.
        Args:
            input_dir (str): Path to the input directory containing the index to register.
            output_dir (str): Path to the output directory where index.json is located.
            index_id (str): The ID to register the index under.
        Returns:
            Output of the kmindex register command.
        Raises:
            FileNotFoundError: If input_dir or output_dir does not exist.
            NotADirectoryError: If input_dir or output_dir is not a directory.
            FileNotFoundError: If index.json does not exist in output_dir.
        """

        input_dir = Toolbox.get_canonical_path(os.path.join(input_dir, index_id))
        output_dir = Toolbox.get_canonical_path(output_dir)

        if not os.path.isdir(input_dir):
            raise NotADirectoryError(
                f"Input directory {input_dir} does not exist or is not a directory"
            )

        if not os.path.isdir(output_dir):
            raise NotADirectoryError(
                f"Output directory {output_dir} does not exist or is not a directory"
            )

        if not Kmindex.b_json_exists(output_dir):
            raise FileNotFoundError(f"index.json not found in {output_dir}")

        if index_id is None:
            index_id = Toolbox.get_basename(input_dir)

        if Kmindex.index_exists_in_json(Kmindex.get_json_path(output_dir), index_id):
            print(
                f"Index ID {index_id} already exists in index.json, skipping registration."
            )
            return

        return Toolbox.run_cmd(
            ["kmindex", "register", "-i", output_dir, "-p", input_dir, "-n", index_id]
        )

    ####################################################
    @staticmethod
    def get_row_count_per_block(sample_count, bytes_per_block=8388608):
        """
        Calculate the number of rows (bitvectors per block) based on the number of samples.
        Args:
            sample_count (int): Number of samples
        Returns:
            int: Number of rows (bitvectors per block)
        """
        return bytes_per_block // Kmindex.get_bytes_per_row(sample_count)

    ####################################################
    @staticmethod
    def query_index(
        names,
        index_path,
        output_dir,
        format,
        fastx,
        zvalue=0,
        threshold=0.0,
        monitor=False,
        is_compressed=False,
    ):
        """
        Run the kmindex query command with the specified parameters.
        Args:
            names (list): List of names to query.
            index_path (str): Path to the index directory.
            output_dir (str): Path to the output directory.
            format (str): Output format (e.g., "json").
            fastx (bool): Whether to use FASTX format.
            zvalue (int): Z-value parameter for the query.
            threshold (float): Threshold parameter for the query.
            monitor (bool): Whether to monitor resource usage.
        Returns:
            Output of the kmindex query command.
        Raises:
            IsADirectoryError: If index_path is not a directory.
            FileNotFoundError: If index.json is missing.
            IsADirectoryError: If output_dir already exists.
        """

        index_path = Toolbox.get_canonical_path(index_path)
        output_dir = Toolbox.get_canonical_path(output_dir)
        if not os.path.isdir(index_path):
            raise NotADirectoryError(
                f"Index path {index_path} does not exist or is not a directory"
            )
        if not Kmindex.b_json_exists(index_path):
            raise FileNotFoundError(f"index.json not found in index path {index_path}")
        if os.path.isdir(output_dir):
            raise IsADirectoryError(
                f"Output directory {output_dir} already exists, please provide a non-existing directory"
            )

        cmd = [
            Bin.get_kmindex_path(),
            "query",
            "--index",
            index_path,
            "--output",
            output_dir,
            "--names",
            ",".join(names),
            "--format",
            format,
            "--fastx",
            fastx,
            "--zvalue",
            str(zvalue),
            "--threshold",
            str(threshold),
        ]

        result = None

        if monitor:
            result = Toolbox.monitor_cmd(cmd)
        else:
            result = Toolbox.run_cmd(cmd)

        if not os.path.isdir(output_dir):
            raise NotADirectoryError(f"Result directory not found: {output_dir}")

        shutil.copy2(fastx, output_dir)

        return result

    @staticmethod
    def compare_query_result_dir(query1: str, query2: str, index: str):
        f1 = os.path.join(query1, f"{index}.json")
        f2 = os.path.join(query2, f"{index}.json")

        if not os.path.isfile(f1):
            raise NotADirectoryError(f"Result file not found: {f1}")

        if not os.path.isfile(f2):
            raise NotADirectoryError(f"Result file not found: {f2}")

        query_res = Kmindex.compare_query_results(f1, f2, index, 1e-9)
        report_diff = Toolbox.json_diff(
            os.path.join(query1, "report.json"), os.path.join(query2, "report.json")
        )
        report_diff.pop("return_code", None)
        return query_res, report_diff

    @staticmethod
    def compare_query_results(
        file1_path: str, file2_path: str, key: str, tolerance: float = 1e-9
    ) -> bool:
        """
        Compare a specific section of two JSON files.

        Args:
            file1_path (str): Path to the first JSON file
            file2_path (str): Path to the second JSON file
            key (str): The first-level key to compare (e.g., "GENOMIC_HUMAN_19")
            tolerance (float): Tolerance for floating point comparisons (default: 1e-9)

        Returns:
            bool: True if the specified sections are equal, False otherwise
        """
        try:
            # Read both JSON files
            with open(file1_path, "r") as f1:
                data1 = json.load(f1)

            with open(file2_path, "r") as f2:
                data2 = json.load(f2)

            # Check if the key exists in both files
            if key not in data1:
                print(f"Error: Key '{key}' not found in {file1_path}")
                return False

            if key not in data2:
                print(f"Error: Key '{key}' not found in {file2_path}")
                return False

            # Compare only the specified sections
            return Kmindex.compare_nested_dicts(data1[key], data2[key], tolerance)

        except FileNotFoundError as e:
            print(f"Error: File not found - {e}")
            return False
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON format - {e}")
            return False
        except Exception as e:
            print(f"Error: {e}")
            return False

    @staticmethod
    def compare_nested_dicts(dict1: dict, dict2: dict, tolerance: float = 1e-9) -> bool:
        """
        Recursively compare two nested dictionaries.
        """
        if not isinstance(dict1, dict) or not isinstance(dict2, dict):
            return Kmindex.compare_values(dict1, dict2, tolerance)

        if set(dict1.keys()) != set(dict2.keys()):
            return False

        for key in dict1.keys():
            if not Kmindex.compare_nested_dicts(dict1[key], dict2[key], tolerance):
                return False

        return True

    @staticmethod
    def compare_values(
        val1: Union[int, float, str], val2: Union[int, float, str], tolerance: float
    ) -> bool:
        """
        Compare two values with floating point tolerance.
        """
        if isinstance(val1, (int, float)) and isinstance(val2, (int, float)):
            return abs(val1 - val2) <= tolerance

        return val1 == val2


#########################################################
# BitmatrixShuffle class
# Contains methods for handling matrix reordering operations
########################################################
class BitmatrixShuffle:
    """Helper class for BitmatrixShuffle (reorder) operations."""

    ####################################################
    @staticmethod
    def parse_ordering_output(lines):
        """
        Parse the bloom matrix reordering output into structured JSON format.

        Args:
            output_text (str): The raw output text from the bitmatrixshuffle processing program

        Returns:
            dict: Parsed data in the specified JSON structure
        """
        result = {}
        matrix_durations = []

        # Parse parameters section
        for i, line in enumerate(lines):
            line = line.strip()

            # Extract basic parameters
            if line.startswith("Index name:"):
                result["index_name"] = line.split(":", 1)[1].strip()
            elif line.startswith("Samples:"):
                result["samples"] = int(line.split(":", 1)[1].strip())
            elif line.startswith("Group size:"):
                result["group_size"] = int(line.split(":", 1)[1].strip())
            elif line.startswith("Subsampled rows:"):
                result["subsampled_rows"] = int(line.split(":", 1)[1].strip())
            elif line.startswith("Block size:"):
                result["block_size"] = int(line.split(":", 1)[1].strip())
            elif line.startswith("Rows per block:"):
                result["rows_per_block"] = int(line.split(":", 1)[1].strip())
            elif line.startswith("Number of blocks:"):
                result["number_of_blocks"] = int(line.split(":", 1)[1].strip())

            # Extract reference matrix number
            elif line.startswith("Transpose submatrix from reference submatrix"):
                # Extract matrix number from path like '/tmp/data/index_1/reordered_GENOMIC_HUMAN_19/matrices/matrix_171.cmbf'
                matrix_match = re.search(r"matrix_(\d+)\.cmbf", line)
                if matrix_match:
                    result["reference_matrix"] = int(matrix_match.group(1))

            # Extract VPTree & NN path duration
            elif line.startswith("VPTree & NN path:"):
                duration_str = line.split(":", 1)[1].strip().replace("s", "")
                result["vptree_nn_duration"] = float(duration_str)

            # Extract matrix reordering durations
            elif line.startswith("Reordering matrix"):
                # The duration is on the next line
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    duration_match = re.search(r"(\d+\.?\d*)s", next_line)
                    if duration_match:
                        duration = float(duration_match.group(1))
                        matrix_durations.append(duration)

        # Add matrix ordering data
        result["matrix_ordering_duration"] = matrix_durations
        result["total_ordering_duration"] = sum(matrix_durations)

        return result

    ####################################################
    @staticmethod
    def reorder_index(output_register_dir, index_id, subsamples_rows):

        sample_count = Kmindex.get_sample_count(output_register_dir, index_id)
        matrix_byte_size = Kmindex.get_bytes_per_matrix(
            Kmindex.get_index_path(output_register_dir, index_id), 1, False
        )
        row_byte_size = Kmindex.get_bytes_per_row(sample_count)
        header_byte_size = Kmindex.get_header_byte_size()

        row_count = Kmindex.get_row_count(
            matrix_byte_size, row_byte_size, header_byte_size
        )

        print(
            f"row_count=({matrix_byte_size} - {header_byte_size}) / {row_byte_size} = {row_count}"
        )

        if subsamples_rows > row_count:
            subsamples_rows = row_count
            print(
                f"Warning: subsamples_rows exceeds max rows {row_count}, using {row_count} instead."
            )

        # Make divisible by 8 (round down)
        if subsamples_rows % 8 != 0:
            original_subsamples = subsamples_rows
            subsamples_rows = (subsamples_rows // 8) * 8
            print(
                f"Warning: subsamples_rows adjusted from {original_subsamples} to {subsamples_rows} (divisible by 8)."
            )

        # Use queues to collect output from threads
        stdout_queue = queue.Queue()
        stderr_queue = queue.Queue()

        def read_stream(stream, prefix, output_queue):
            for line in stream:
                line_stripped = line.rstrip()
                print(f"{prefix} {line_stripped}")  # LIVE OUTPUT IN CONSOLE
                output_queue.put(line_stripped)
            output_queue.put(None)  # Signal end of stream

        try:
            print("Starting subprocess...")

            cmd = [
                Bin.get_reorderer_path(),
                "-i",
                output_register_dir,
                "-n",
                index_id,
                "-s",
                str(subsamples_rows),
            ]

            print(f"Running command: {' '.join(cmd)}")

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )

            # Start threads to read both streams
            stdout_thread = threading.Thread(
                target=read_stream, args=(process.stdout, "     1:", stdout_queue)
            )
            stderr_thread = threading.Thread(
                target=read_stream, args=(process.stderr, "     2:", stderr_queue)
            )

            stdout_thread.start()
            stderr_thread.start()

            # Wait for process to complete
            return_code = process.wait()

            # Wait for all output to be read
            stdout_thread.join()
            stderr_thread.join()

            # Collect all output from queues
            stdout_lines = []
            stderr_lines = []

            while True:
                line = stdout_queue.get()
                if line is None:
                    break
                stdout_lines.append(line)

            while True:
                line = stderr_queue.get()
                if line is None:
                    break
                stderr_lines.append(line)

            print(f"Process completed with return code: {return_code}")

            return {
                "returncode": return_code,
                "stdout": stdout_lines,
                "stderr": stderr_lines,
            }

        except Exception as e:
            print(f"Error: {e}")
            return None


##########################################################
# BlockCompressorZSTD class
# Contains methods for handling matrix compression operations
##########################################################


class BlockCompressorZSTD:
    """Helper class for BlockCompressorZSTD (compression) operations."""

    ####################################################
    # Example usage:
    # samples = 1000
    # rows = calculate_rows(samples, "output.txt")
    # print(f"Configuration written to output.txt")
    @staticmethod
    def create_config_file(samples, output_file="config.cfg"):
        """
        Calculate rows and write configuration to output file.

        Args:
            samples (int): Number of samples
            output_file (str): Path to output file

        Returns:
            int: Number of rows (bitvectors per block)
        """
        rows = Kmindex.get_row_count_per_block(samples)

        # Write to output file
        with open(output_file, "w") as f:
            f.write(f"samples = {samples}\n")
            f.write(f"bitvectorsperblock = {rows}\n")
            f.write("preset = 3\n")  # Default Zstd preset

        return rows

    ####################################################
    @staticmethod
    def compress_matrix(*args):
        """
        Run the BlockCompressorZSTD compression script with the specified arguments.
        Args:
            args: Arguments to pass to the compression script
        Returns:
            Output of the compression script.
        """
        return Toolbox.run_cmd([Bin.get_compressor_path()] + list(args))

    ####################################################
    @DeprecationWarning
    @staticmethod
    def compress_index(input_dir, output_dir, index_id, full_check_enabled=True):
        """
        Compress the matrices of a given index using BlockCompressorZSTD.
        Args:
            input_dir (str): Path to the input directory containing the index to compress.
            index_id (str): The ID of the index to compress.
            full_check_enabled (bool): Whether to perform full validation checks before compression.
        Returns:
            None
        Raises:
            FileNotFoundError: If input_dir or output_dir does not exist.
            NotADirectoryError: If input_dir or output_dir is not a directory.
            FileNotFoundError: If index.json does not exist in input_dir.
            NotADirectoryError: If the specified index does not exist in input_dir.
        """

        raise NotImplementedError("Deprecated... Use class Compressor instead")

        input_dir = Toolbox.get_canonical_path(input_dir)
        output_dir = Toolbox.get_canonical_path(output_dir)

        if not os.path.isdir(input_dir):
            raise NotADirectoryError(
                f"Input directory {input_dir} does not exist or is not a directory"
            )

        if not os.path.isdir(output_dir):
            raise NotADirectoryError(
                f"Output directory {output_dir} does not exist or is not a directory"
            )

        input_index_path = Kmindex.get_index_path(input_dir, index_id)
        output_index_path = Kmindex.get_index_path(output_dir, index_id)

        if not Kmindex.b_json_exists(input_dir):
            raise FileNotFoundError(f"index.json not found in {input_dir}")

        if not Kmindex.b_index_exists(input_dir, index_id):
            raise NotADirectoryError(
                f"Index ID {index_id} does not exist in input directory {input_dir}"
            )

        if not os.path.isdir(Kmindex.get_matrix_dir(input_index_path)):
            raise NotADirectoryError(
                f"Input directory {input_index_path} does not contain a matrices subdirectory"
            )

        if not os.path.isdir(Kmindex.get_matrix_dir(output_index_path)):
            raise NotADirectoryError(
                f"Output directory {output_index_path} does not contain a matrices subdirectory"
            )

        if full_check_enabled:
            Kmindex.validate_index_ids(
                [index_id],
                Kmindex.read_index_ids_from_json(Kmindex.get_json_path(input_dir)),
            )
            Kmindex.check_index_structure(input_index_path)

        # if os.path.exists(output_index_path):
        #     raise FileExistsError(
        #         f"Output index path {output_index_path} already exists"
        # )

        nb_samples = Kmindex.read_index_value(input_dir, index_id, "nb_samples")
        np_partitions = Kmindex.read_index_value(input_dir, index_id, "nb_partitions")

        config_file_path = os.path.join(output_index_path, "config.cfg")
        BlockCompressorZSTD.create_config_file(nb_samples, config_file_path)

        for partition in range(np_partitions):
            print(f"Compressing partition {partition}...")

            original_path = Kmindex.get_matrix_path(output_index_path, partition)
            compressed_path = Kmindex.get_matrix_path(
                output_index_path, partition, is_compressed=True
            )

            res = BlockCompressorZSTD.compress_matrix(
                original_path,
                config_file_path,
                Kmindex.get_header_byte_size(),
                compressed_path,
            )

            original_size = os.path.getsize(original_path)
            compressed_size = os.path.getsize(compressed_path)

            if compressed_size >= original_size:
                print(
                    f"Warning: Compressed file ({compressed_size} bytes) is not smaller than original ({original_size} bytes) for partition {partition}"
                )

            os.remove(original_path)

            print(res)
