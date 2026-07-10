import logging
import os
import shutil

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
