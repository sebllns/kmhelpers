import datetime
import json
import os
import queue
import re
import shutil
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional, Tuple, Union

import psutil


class Main:
    """Main initialization class for kmhelpers."""

    ####################################################
    @staticmethod
    def init(default_bin_path: str = "./bin", check_all: bool = True, chdir: str = "") -> None:
        """
        Initialize kmhelpers by setting up binary paths and checking dependencies.

        Args:
            default_bin_path: Default path for binary executables (default: "./bin").
            check_all: If True, verify all required binaries are available (default: True).
            chdir: If non-empty, change the working directory to this path before initialization.
        """
        if chdir:
            print(f"cd {chdir}")
            os.chdir(chdir)
        Bin.set_default_bin_path(default_bin_path)
        Bin.add_bin_dir_to_syspath()
        print(f"KMHELPERS_BIN_PATH={Bin.get_bin_dir()}")
        os.makedirs(Bin.get_bin_dir(), exist_ok=True)
        if check_all:
            Bin.check_all()


#########################################################
# Bin class
# Contains methods for binary path management and validation
########################################################
class Bin:
    """Binary path management and validation utilities."""

    ####################################################
    @staticmethod
    def set_default_bin_path(path: str) -> None:
        """
        Set the default binary path if not already set.

        Args:
            path: Path to the binary directory
        """
        os.environ.setdefault("KMHELPERS_BIN_PATH", Toolbox.get_canonical_path(path))

    ####################################################
    @staticmethod
    def fetch(binary: str, path: str) -> None:
        """
        Fetch a binary from a given path and create a symlink in the bin directory.

        Args:
            binary: Name of the binary
            path: Source path of the binary

        Raises:
            AssertionError: If the source binary is not found
        """
        bin_path = Bin.get_bin_path(binary)
        if not os.path.isfile(bin_path):
            assert os.path.isfile(path), f"Binary not found: {path}"
            print(f"Linking {path} to {bin_path}")
            os.symlink(path, bin_path)

    ####################################################
    @staticmethod
    def get_bin_dir() -> str:
        """
        Get the binary directory path.

        Returns:
            The canonical path to the binary directory

        Raises:
            RuntimeError: If Main.init() hasn't been called
        """
        if "KMHELPERS_BIN_PATH" not in os.environ:
            raise RuntimeError(
                "Main.init() must be called at program startup before using get_bin_dir()"
            )
        return Toolbox.get_canonical_path(os.environ["KMHELPERS_BIN_PATH"])

    ####################################################
    @staticmethod
    def get_bin_path(binary: str) -> str:
        """
        Get the full path to a binary executable.

        Args:
            binary: Name of the binary

        Returns:
            Full path to the binary
        """
        return os.path.join(Bin.get_bin_dir(), binary)

    ####################################################
    @staticmethod
    def add_bin_dir_to_syspath() -> None:
        """Add the binary directory to the system PATH."""
        os.environ["PATH"] = (
            f"{Bin.get_bin_dir()}{os.pathsep}{os.environ.get('PATH', '')}"
        )

    ####################################################
    @staticmethod
    def kmindex() -> str:
        """Get the kmindex binary name."""
        return "kmindex"

    ####################################################
    @staticmethod
    def compressor() -> str:
        """Get the compressor binary name."""
        return "block_compressor_bin"

    ####################################################
    @staticmethod
    def decompressor() -> str:
        """Get the decompressor binary name."""
        return "block_decompressor_bin"

    ####################################################
    @staticmethod
    def reorderer() -> str:
        """Get the reorderer binary name."""
        return "main_bitmatrixshuffle"

    ####################################################
    @staticmethod
    def check_bin(binary_name: str) -> None:
        """
        Check if a binary exists in PATH and print a warning if not found.

        Args:
            binary_name: Name of the binary to check
        """
        if not shutil.which(binary_name):
            print(f"Warning: {binary_name} command not found in PATH")

    ####################################################
    @staticmethod
    def check_kmindex() -> None:
        """
        Check if kmindex is available with helpful error message.

        Raises:
            RuntimeError: If kmindex >= 0.5.3 is not found in PATH
        """
        kmindex_path = shutil.which(Bin.kmindex())
        if not kmindex_path:
            raise RuntimeError(
                f"kmindex >= 0.5.3 is required but not found in PATH.\n"
                f"\n"
                f"Install via bioconda:\n"
                f"  conda install -c bioconda kmindex>=0.5.3\n"
                f"\n"
                f"Or compile from source and add to PATH:\n"
                f"  export PATH=/path/to/kmindex/build:$PATH\n"
                f"\n"
                f"Verify installation:\n"
                f"  kmindex --version"
            )

    ####################################################
    @staticmethod
    def check_all() -> None:
        """Check all required binaries are available in PATH."""
        binaries = [
            Bin.kmindex(),
            Bin.reorderer(),
            Bin.compressor(),
            Bin.decompressor(),
        ]

        for binary in binaries:
            Bin.check_bin(binary)


#########################################################
# toolbox class
# Contains utility methods for file and path operations
########################################################
class Toolbox:
    """Utility class for common operations."""

    ####################################################
    @staticmethod
    def get_size(filename: str) -> int:
        return os.stat(filename).st_size

    ####################################################
    @staticmethod
    def json_serialize(data: Any, filename: str, pretty: bool = True) -> None:
        """
        Save JSON data directly to a file.

        Args:
            data: The JSON-serializable data to save
            filename: Path where to save the JSON file
            pretty: Whether to format JSON with indentation (default: True)
        """
        with open(filename, "w") as f:
            if pretty:
                json.dump(data, f, indent=2)
            else:
                json.dump(data, f)

        print(f"JSON data saved to: {filename}")

    ####################################################
    @staticmethod
    def json_diff(file1_path: str, file2_path: str) -> Dict[str, Any]:
        """
        Calculate the difference between two JSON files.

        Args:
            file1_path: Path to the first JSON file
            file2_path: Path to the second JSON file

        Returns:
            Dictionary containing the differences between the two JSON files
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
    def get_canonical_path(path: str) -> str:
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
    def get_basename(path: str) -> str:
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
    def read_stream(stream: Any, prefix: str) -> None:
        """
        Read and print lines from a stream with a prefix.

        Args:
            stream: Input stream to read from
            prefix: Prefix to add to each line
        """
        for line in stream:
            print(f"{prefix}: {line.rstrip()}")

    ####################################################
    @staticmethod
    def get_posix_timestamp() -> int:
        """
        Get the current POSIX timestamp.

        Returns:
            Current timestamp in seconds since Unix epoch
        """
        return int(time.time())

    ####################################################
    @staticmethod
    def get_human_readable_timestamp() -> str:
        """
        Get the current timestamp in human-readable format.

        Returns:
            Timestamp formatted as "YYYY-MM-DD HH:MM:SS"
        """
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    ####################################################
    @staticmethod
    def run_cmd(cmd: List[Any], trace: bool = True) -> str:
        """
        Run a command using subprocess and capture its output.

        Args:
            cmd: Command and arguments as a list (converted to List[str])
            trace: Whether to print command output (default: True)

        Returns:
            Standard output from the command

        Raises:
            subprocess.SubprocessError: If command returns non-zero exit code
        """
        if trace:
            print("Running command:", *cmd)

        result = subprocess.run(
            [str(arg) for arg in cmd], capture_output=True, text=True
        )

        if trace:
            for line in result.stdout.strip().split("\n"):
                if line:
                    print(f"1: {line}")
            for line in result.stderr.strip().split("\n"):
                if line:
                    print(f"2: {line}")

        if result.returncode != 0:
            raise subprocess.SubprocessError(
                f"Command {cmd[0]} returned code {result.returncode}\nLog: {result.stderr}"
            )

        return result.stdout

    ####################################################
    @staticmethod
    def monitor_cmd(
        cmd: List[str], print_trace: bool = True, log_file: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Run a command and monitor its resource usage.

        Args:
            cmd: Command and arguments as a list.
            print_trace: If True, print command output to stdout in real time (default: True).
            log_file: Optional path to write stdout/stderr to.

        Returns:
            dict: Resource stats with keys `start_time`, `execution_time_ms`,
            `max_cpu_percent`, `max_memory_mb`, `return_code`, and `error`.
            Returns None if the process cannot be started.
        """

        max_cpu = 0.0
        max_memory = 0.0
        monitoring = True
        monitor_lock = threading.Lock()

        def monitor_resources(process):
            nonlocal max_cpu, max_memory, monitoring
            try:
                psutil_process = psutil.Process(process.pid)
                psutil_process.cpu_percent(interval=0.1)

                while monitoring and process.poll() is None:
                    try:
                        processes = [psutil_process] + psutil_process.children(
                            recursive=True
                        )

                        cpu_percent = sum(p.cpu_percent() for p in processes)
                        memory_bytes = sum(p.memory_info().rss for p in processes)
                        memory_mb = memory_bytes / 1024 / 1024

                        with monitor_lock:
                            max_cpu = max(max_cpu, cpu_percent)
                            max_memory = max(max_memory, memory_mb)

                        time.sleep(0.1)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        break
            except Exception as e:
                print(f"Resource monitoring error: {e}")

        try:
            start_time = time.time()
            result = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )

            monitor_thread = threading.Thread(target=monitor_resources, args=(result,))
            monitor_thread.daemon = True
            monitor_thread.start()
            time.sleep(0.01)

            stdout, stderr = result.communicate()
            end_time = time.time()
            monitoring = False
            monitor_thread.join(timeout=1)

            execution_time = 1000 * (end_time - start_time)

            with monitor_lock:
                output = {
                    "command": " ".join(cmd),
                    "start_time": start_time,
                    "execution_time_ms": round(execution_time, 4),
                    "max_cpu_percent": round(max_cpu, 4),
                    "max_memory_mb": round(max_memory, 4),
                    "return_code": result.returncode,
                    "stdout": stdout,
                    "stderr": stderr,
                }

            # Build output content
            output_lines = [
                f"Command: {output['command']}",
                f"Execution time: {output['execution_time_ms']}ms",
                f"Max CPU: {output['max_cpu_percent']}%",
                f"Max Memory: {output['max_memory_mb']} MB",
                f"Return code: {output['return_code']}",
                "\n--- STDOUT ---",
                stdout,
            ]
            if stderr.strip():
                output_lines.extend(["\n--- STDERR ---", stderr])

            output_content = "\n".join(output_lines) if log_file or print_trace else ""

            # Print to console if print_trace is enabled
            if print_trace:
                print(output_content)

            # Write to log file if specified
            if log_file:
                print(f"Logging output to: {log_file}")
                with open(log_file, "w") as f:
                    f.write(output_content)

            return output

        except Exception as e:
            print(f"Failed to start process: {e}")
            return None


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
    def get_header_byte_size() -> int:
        """
        Get the size of the matrix file header.

        Returns:
            Header size in bytes (49 bytes)
        """
        return 49

    ####################################################
    @staticmethod
    def compare_matrices_size(
        folders: List[str], type: List[str], index: str
    ) -> Dict[str, Any]:
        """Compare matrix sizes across folders and partitions.

        Args:
            folders: List of folder paths to analyze.
            type: List of matrix types to include in the comparison.
            index: Index identifier used to locate partitions within each folder.

        Returns:
            Dictionary containing analysis results with folder sizes and matrix sizes.
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
    def check_index_structure(directory_path, partition_count=256) -> bool:
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
    def version():
        return Toolbox.run_cmd([Bin.kmindex(), "--version"])

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
    def get_row_count(
        matrix_byte_size: int, row_byte_size: int, header_byte_size: int
    ) -> int:
        assert matrix_byte_size > 0
        assert row_byte_size > 0
        assert header_byte_size >= 0
        return (matrix_byte_size - header_byte_size) // row_byte_size

    ####################################################
    @staticmethod
    def get_bytes_per_matrix(
        index_path: str, partition: int, is_compressed: bool = False
    ) -> int:
        return BlockCompressorZSTD.get_file_byte_size(
            Kmindex.get_matrix_path(index_path, partition, is_compressed), is_compressed
        )

    ####################################################
    @staticmethod
    def get_bytes_per_row(sample_count: int) -> int:
        """
        Calculate the number of bytes needed to store one row of bitvectors.

        Each sample is represented by 1 bit, so bytes_per_row = ceil(sample_count / 8).

        Args:
            sample_count: Number of samples in the index

        Returns:
            Number of bytes per row
        """
        return (sample_count + 7) // 8

    ####################################################
    @staticmethod
    def get_partition_count(input_dir: str, index_id: str) -> int:
        """
        Get the number of partitions for an index.

        Args:
            input_dir: Directory containing the index.json file
            index_id: The index ID to query

        Returns:
            Number of partitions in the index
        """
        return Kmindex.read_index_value(input_dir, index_id, "nb_partitions")

    ####################################################
    @staticmethod
    def get_sample_count(input_dir: str, index_id: str) -> int:
        """
        Get the number of samples for an index.

        Args:
            input_dir: Directory containing the index.json file
            index_id: The index ID to query

        Returns:
            Number of samples in the index
        """
        return Kmindex.read_index_value(input_dir, index_id, "nb_samples")

    ####################################################
    @staticmethod
    def read_index_value(input_dir: str, index_id: str, key: str) -> Any:
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
    def get_matrix_dir(index_path: str) -> str:
        """
        Get the path to the matrices directory within an index.

        Args:
            index_path: Path to the index directory

        Returns:
            Canonical path to the matrices directory
        """
        return Toolbox.get_canonical_path(os.path.join(index_path, "matrices"))

    ####################################################
    @staticmethod
    def get_matrix_path(
        index_path: str, partition: int, is_compressed: bool = False
    ) -> str:
        """
        Get the path to a specific matrix partition file.

        Args:
            index_path: Path to the index directory
            partition: Partition number
            is_compressed: Whether to get the compressed matrix path (default: False)

        Returns:
            Path to the matrix file (either matrix_N.cmbf or blocks_N for compressed)
        """
        return os.path.join(
            Kmindex.get_matrix_dir(index_path),
            f"blocks_{partition}" if is_compressed else f"matrix_{partition}.cmbf",
        )

    ####################################################
    @staticmethod
    def get_ef_path(index_path: str, partition: int) -> str:
        """
        Get the path to the Elias-Fano encoded file for a compressed partition.

        Args:
            index_path: Path to the index directory
            partition: Partition number

        Returns:
            Path to the .ef file
        """
        return BlockCompressorZSTD.get_ef_path(
            Kmindex.get_matrix_path(index_path, partition, True)
        )

    ####################################################
    @staticmethod
    def get_compressed_files_path(index_path: str, partition: int) -> Tuple[str, str]:
        """
        Get paths to both compressed matrix files (blocks and .ef).

        Args:
            index_path: Path to the index directory
            partition: Partition number

        Returns:
            Tuple of (blocks_path, ef_path)
        """
        return Kmindex.get_matrix_path(
            index_path, partition, True
        ), Kmindex.get_ef_path(index_path, partition)

    ####################################################
    @staticmethod
    def get_index_path(root: str, index: str) -> str:
        """
        Get the full path to an index directory.

        Args:
            root: Root directory containing indices
            index: Index ID or name

        Returns:
            Canonical path to the index directory
        """
        return Toolbox.get_canonical_path(os.path.join(root, index))

    ####################################################
    @staticmethod
    def get_path_inside_index(root: str, file: str) -> str:
        """
        Get the full path to a file within an index directory.

        Args:
            root: Index root directory
            file: Relative file path within the index

        Returns:
            Canonical path to the file
        """
        return Toolbox.get_canonical_path(os.path.join(root, file))

    ####################################################
    @staticmethod
    def get_build_info_path(root: str) -> str:
        """Get the path to build_infos.txt within an index directory."""
        return Kmindex.get_path_inside_index(root, "build_infos.txt")

    ####################################################
    @staticmethod
    def get_fof_path(root: str) -> str:
        """Get the path to kmtricks.fof file within an index directory."""
        return Kmindex.get_path_inside_index(root, "kmtricks.fof")

    ####################################################
    @staticmethod
    def get_options_path(root: str) -> str:
        """Get the path to options.txt file within an index directory."""
        return Kmindex.get_path_inside_index(root, "options.txt")

    ####################################################
    @staticmethod
    def get_json_path(root: str) -> str:
        """Get the path to index.json file within a directory."""
        return Kmindex.get_path_inside_index(root, "index.json")

    ####################################################
    @staticmethod
    def b_json_exists(root: str) -> bool:
        """
        Check if index.json exists in the given directory.

        Args:
            root: Directory to check

        Returns:
            True if index.json exists
        """
        return os.path.isfile(Kmindex.get_json_path(root))

    ####################################################
    @staticmethod
    def b_index_exists(root: str, index: str) -> bool:
        """
        Check if an index directory exists.

        Args:
            root: Root directory containing indices
            index: Index ID to check

        Returns:
            True if the index directory exists
        """
        return os.path.isdir(Kmindex.get_index_path(root, index))

    ####################################################
    @staticmethod
    def register_index_in_json(input_dir, output_dir, index_id):
        """Register a new index in the index.json file located in the output directory.

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
            [
                Bin.kmindex(),
                "register",
                "-i",
                output_dir,
                "-p",
                input_dir,
                "-n",
                index_id,
            ]
        )

    ####################################################
    @staticmethod
    def get_row_count_per_block(sample_count: int, bytes_per_block: int = 8388608) -> int:
        """Calculate the number of rows (bitvectors per block) based on sample count.

        Args:
            sample_count (int): Number of samples.
            bytes_per_block (int): Block size in bytes (default: 8388608 = 8 MB).

        Returns:
            int: Number of rows (bitvectors per block).
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
        is_compressed=False,
    ) -> dict:
        """Run the kmindex query command with the specified parameters.

        Args:
            names (list): List of index IDs to query.
            index_path (str): Path to the index directory.
            output_dir (str): Path to the output directory.
            format (str): Output format (e.g., ``"json"``).
            fastx (bool): Whether to use FASTX format for the query file.
            zvalue (int): Z-value parameter for the query.
            threshold (float): Threshold parameter for the query.
            is_compressed (bool): Whether the index is stored in compressed form.

        Returns:
            dict: Output of the kmindex query command.
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
            Bin.kmindex(),
            "query",
            "--index",
            index_path,
            "--output",
            output_dir,
            "--format",
            format,
            "--fastx",
            fastx,
            "--zvalue",
            str(zvalue),
            "--threshold",
            str(threshold),
        ]

        if names:
            cmd.extend(
                [
                    "--names",
                    ",".join(names),
                ]
            )

        result = Toolbox.monitor_cmd(cmd)

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
    def create_config_file(samples, output_file="config.cfg") -> int:
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
    def get_ef_path(path: str) -> str:
        return path + ".ef"

    ####################################################
    @staticmethod
    def get_file_byte_size(path: str, is_compressed: bool) -> int:
        return Toolbox.get_size(path) + (
            Toolbox.get_size(BlockCompressorZSTD.get_ef_path(path))
            if is_compressed
            else 0
        )

    ####################################################
    @staticmethod
    def compress(
        input_matrix_path: str,
        matrix_columns_count: int,
        permutation_path: str,
        output_compressed_path: str,
        config_path: str,
        output_metric_path: str = "",
        block_size: int = 8388608,
        group_size: int = 0,
        subsample_size: int = 0,
        threshold: int = 0,
        disable_reorder: bool = False,
    ) -> dict:
        """Run the BlockCompressorZSTD compression script.

        Args:
            input_matrix_path (str): Path to the input matrix file.
            matrix_columns_count (int): Number of columns in the matrix.
            permutation_path (str): Path to the permutation file.
            output_compressed_path (str): Path for the compressed output.
            config_path (str): Path to write the compression config.
            output_metric_path (str): Optional path to write compression metrics.
            block_size (int): Block size in bytes (default: 8388608 = 8 MB).
            group_size (int): Group size for compression (0 = auto).
            subsample_size (int): Subsample size for reordering (0 = disabled).
            threshold (int): Threshold for reordering (0 = disabled).
            disable_reorder (bool): If True, skip the reordering step.

        Returns:
            dict: Output of the compression script.
        """

        # Check input_matrix_path exists
        if not os.path.exists(input_matrix_path):
            raise FileNotFoundError(f"Input matrix file not found: {input_matrix_path}")

        if matrix_columns_count <= 0:
            raise ValueError("Matrix columns count must be greater than zero")

        cmd = [
            Bin.reorderer(),
            "-i",
            input_matrix_path,
            "-c",
            str(matrix_columns_count),
            "--header",
            "49",
        ]

        if group_size > 0:
            cmd.extend(["-g", str(group_size)])

        if subsample_size > 0:
            cmd.extend(["-s", str(subsample_size)])

        if block_size > 0:
            cmd.extend(["-b", str(block_size)])

        if disable_reorder:
            cmd.append("-n")

        if permutation_path:
            cmd.extend(
                ["-f" if os.path.isfile(permutation_path) else "-t", permutation_path]
            )

        if output_compressed_path:
            cmd.extend(["-z", output_compressed_path])

        if output_metric_path:
            cmd.extend(["-j", output_metric_path])

        if config_path:
            cmd.extend(["--config-path", config_path])

        if threshold > 0:
            cmd.extend(["--threshold", str(threshold)])

        return Toolbox.run_cmd(cmd)

    ####################################################
    @staticmethod
    def decompress(
        input: str,
        matrix_columns_count: int,
        output: str,
        config_path: str,
    ):
        # Check input_matrix_path exists
        if not os.path.exists(input):
            raise FileNotFoundError(f"Input matrix file not found: {input}")

        if matrix_columns_count <= 0:
            raise ValueError("Matrix columns count must be greater than zero")

        cmd = [
            Bin.decompressor(),
            config_path,
            input,
            BlockCompressorZSTD.get_ef_path(input),
            "49",
            output,
        ]

        return Toolbox.run_cmd(cmd)

    ####################################################
    @staticmethod
    def reverse_permutation(
        input_matrix_path: str,
        matrix_columns_count: int,
        permutation_path: str,
    ):
        cmd = [
            Bin.reorderer(),
            "-i",
            input_matrix_path,
            "-f",
            permutation_path,
            "-c",
            str(matrix_columns_count),
            "--header",
            "49",
            "-r",
        ]

        return Toolbox.run_cmd(cmd)
