import json
import logging
import os
import shutil
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import psutil

logger = logging.getLogger(__name__)


class Main:
    """Main initialization class for kmhelpers."""

    ####################################################
    @staticmethod
    def init(
        default_bin_path: str = "./bin", check_all: bool = True, chdir: str = ""
    ) -> None:
        """
        Initialize kmhelpers by setting up binary paths and checking dependencies.

        Args:
            default_bin_path: Default path for binary executables (default: "./bin").
            check_all: If True, verify all required binaries are available (default: True).
            chdir: If non-empty, change the working directory to this path before initialization.
        """
        if chdir:
            logger.info(f"cd {chdir}")
            os.chdir(chdir)
        Bin.set_default_bin_path(default_bin_path)
        Bin.add_bin_dir_to_syspath()
        logger.info(f"KMHELPERS_BIN_PATH={Bin.get_bin_dir()}")
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
            logger.info(f"Linking {path} to {bin_path}")
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
    def check_bin(binary_name: str) -> None:
        """
        Check if a binary exists in PATH and print a warning if not found.

        Args:
            binary_name: Name of the binary to check
        """
        if not shutil.which(binary_name):
            logger.warning(f"{binary_name} command not found in PATH")

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
            logger.info("Running command: " + " ".join(str(arg) for arg in cmd))

        result = subprocess.run(
            [str(arg) for arg in cmd], capture_output=True, text=True
        )

        if trace:
            for line in result.stdout.strip().split("\n"):
                if line:
                    logger.info(f"1: {line}")
            for line in result.stderr.strip().split("\n"):
                if line:
                    logger.info(f"2: {line}")

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
            nonlocal max_cpu, max_memory
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
                logger.error(f"Resource monitoring error: {e}")

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

            # Log output if print_trace is enabled
            if print_trace:
                logger.info(output_content)

            # Write to log file if specified
            if log_file:
                logger.info(f"Logging output to: {log_file}")
                with open(log_file, "w") as f:
                    f.write(output_content)

            return output

        except Exception as e:
            logger.error(f"Failed to start process: {e}")
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

        logger.info(f"Created empty index.json at: {output_file}")
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
            logger.error(f"Directory '{directory_path}' does not exist!")
            return False

        logger.info(f"Checking index structure in: {directory_path}")

        # Check each expected item
        for item in sorted(all_expected):
            item_path = os.path.join(directory_path, item)

            if not os.path.exists(item_path):
                missing_items.append(item)
                all_present = False

        # Report results
        if missing_items:
            logger.warning(f"MISSING ITEMS ({len(missing_items)}):")
            logger.warning("-" * 30)

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
                logger.warning("Root files:")
                for item in missing_root_files:
                    logger.warning(f"  - {item}")

            if missing_dirs:
                logger.warning("Directories:")
                for item in missing_dirs:
                    logger.warning(f"  - {item}/")

            if missing_config:
                logger.warning("Config files:")
                for item in missing_config:
                    logger.warning(f"  - {item}")

            if missing_repartition:
                logger.warning("Repartition files:")
                for item in missing_repartition:
                    logger.warning(f"  - {item}")

            if missing_matrices:
                logger.warning(f"Matrix files ({len(missing_matrices)}):")
                # Show first few and last few if many are missing
                if len(missing_matrices) > 10:
                    for item in missing_matrices[:5]:
                        logger.warning(f"  - {item}")
                    logger.warning(f"  ... ({len(missing_matrices) - 10} more)")
                    for item in missing_matrices[-5:]:
                        logger.warning(f"  - {item}")
                else:
                    for item in missing_matrices:
                        logger.warning(f"  - {item}")

        return all_present

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
            logger.info(
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


##########################################################
# BlockCompressorZSTD class
# Contains methods for handling matrix compression operations
##########################################################
class BlockCompressorZSTD:
    """Helper class for BlockCompressorZSTD (compression) operations."""

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
