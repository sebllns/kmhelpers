# Changelog

All notable changes to this project will be documented in this file.

## [0.3.0] - 2025-11-20

### Added

- **KmindexWrapper**: High-level interface for building and querying kmindex indices
  - `build()` method wraps kmindex build with all parameters
  - `query()` method wraps kmindex query functionality
  - Automatic handling of required parameters (`-d/--run-dir`, `-r/--register-as`)
  - Returns `KmtricksIndex` objects for easy property access
  - Support for both presence/absence and abundance indexing

- **FofManager**: Comprehensive file-of-files (FOF) management class
  - `create_fof_file()`: Create FOF from list of files with smart sample name extraction
  - `create_fof_from_directory()`: Auto-discover and create FOF from directory
  - `list_files_in_directory()`: List files matching bioinformatics extensions
  - `load_fof_file()` / `get_sample_ids()`: Load sample IDs from FOF
  - `load_with_paths()`: Load samples with their file paths as dictionary
  - `validate_fof_file()`: Comprehensive FOF format validation
  - `validate_input_files()`: Batch file existence checking
  - `extract_sample_name()`: Smart extraction removing common extensions (.fasta.gz, .fastq.gz, etc.)
  - `append_to_fof()`: Append files to existing FOF
  - `copy_fof()`: Copy FOF files
  - Support for recursive directory scanning
  - Configurable file extension filtering

- **New core module**: `kmhelpers/core/wrapper.py` for KmindexWrapper
- **New operations module**: `kmhelpers/operations/fof.py` for FofManager
- **Example script**: `examples/index_fake_samples.py` demonstrating new wrapper usage
- **Example data**: `examples/data/fake_samples/` with synthetic FASTA files for testing

### Changed

- Updated `KmindexWrapper` to use `FofManager` for FOF operations
- Type annotations improved using `Sequence` instead of `List` for better type compatibility
- Updated package version to 0.3.0 in `__init__.py`
- Enhanced README.md with comprehensive documentation for new features
- Added quick start section for building indices
- Updated API reference with KmindexWrapper and FofManager documentation

### Fixed

- Fixed kmindex build command to always include required `-d/--run-dir` parameter (defaults to `.kmindex_run`)
- Fixed kmindex build command to always include required `-r/--register-as` parameter (defaults to index basename)
- Added validation to check if `run_dir` already exists to prevent build errors
- Fixed type compatibility issues with file list parameters using `Sequence` type hint
- Corrected FOF format to use "name: path" (with colon separator) instead of just path

### Documentation

- Updated README.md with new features section
- Added FOF management examples
- Added index building examples with KmindexWrapper
- Updated project structure documentation
- Updated API reference with new classes and methods
- Updated examples/data/fake_samples/README.md with corrected kmindex parameters

## [0.2.0] - 2024-11-19

### Added

- **Type Annotations**: Complete type annotations for all methods in `utils.py`
- **Index Structure Validation**:
  - `check_index_structure()`: Comprehensive validation of index directory structure
  - `create_registry_from_folder()`: Auto-discover and register multiple indices from a folder
- **Binary Version Management**:
  - `get_kmindex_version()`: Wrapper to retrieve kmindex version
  - Optional binary checks with `Main.init(check_bins=False)`
- **Index Registry Improvements**:
  - Better error handling and validation
  - Fixed bugs in index property loading
  - Improved JSON import/export
- **Installation Tools**:
  - `install_kmindex.sh`: Script to install kmindex without server dependencies
  - Improved dependency checking
- **Compression Enhancements**:
  - Support for compressing indices outside their directory
  - Improved BitmatrixShuffle wrapper calls
  - Added reverse permutation validation tests
  - Enhanced size comparison path handling
- **Examples**:
  - `compress_selection.py`: Example for selective partition compression
  - Sample data added for testing
  - Bash script to run examples

### Changed

- **Binary Management**:
  - Updated PATH management system for external binaries
  - More flexible binary location handling
- **Class Renaming**:
  - Internal class reorganization for consistency
- **Compressor Updates**:
  - Multiple iterations of compressor improvements
  - Better API for compression operations
  - Enhanced metrics collection
- **Index Parameter**: Made index a required input parameter for operations
- **Setup.py**: Multiple updates for better package configuration

### Fixed

- Type issues in index property handling
- Path handling for size comparison files
- Package installation issues
- Index registry bugs
- JSON index import issues
- Misindenting in core modules
- Binary check dependency issues

### Documentation

- Improved log messages for index structure validation
- Updated documentation for new features
- Corrected incorrect information in API docs
- Added author information

## [0.0.1] - 2024-10-28

### Restructured

- **Complete project reorganization** for better maintainability and professionalism
  - Created modular package structure with `core/`, `operations/`, `metrics/`, and `cli/` submodules
  - Moved `kmhelpers.py` → `kmhelpers/core/utils.py`
  - Organized related functionality into logical modules
  - Added proper `__init__.py` files for clean package imports

### Added

- **Comprehensive README.md** with:
  - Project overview and features
  - Installation instructions
  - Quick start guide
  - Complete API reference
  - Multiple usage examples
  - Performance tips and troubleshooting

- **setup.py** for proper Python package installation
  - Support for `pip install -e .`
  - Console script entry points (`kmhelpers-query`, `kmhelpers-compress`)
  - Proper dependencies declaration

- **Documentation**:
  - `examples/basic_usage.py` - Basic usage example

### Deprecated

- Direct script execution (still works but CLI commands preferred):
  ```bash
  # Old
  python query_index.py

  # New
  kmhelpers-query  # or python -m kmhelpers.cli.query_index
  ```

## Project Structure

```
kmhelpers/
├── kmhelpers/              # Main package
│   ├── core/              # Core functionality
│   │   ├── utils.py       # Binary management, utilities, kmindex operations
│   │   └── index.py       # Index and IndexRegistry classes
│   ├── operations/        # Compression operations
│   │   └── compressor.py  # Compressor class
│   ├── metrics/           # Performance metrics
│   │   └── compression_metrics.py
│   └── cli/               # Command-line tools
│       ├── compress_index.py
│       ├── query_index.py
│       └── register_index.py
├── examples/              # Usage examples
├── tests/                 # Unit tests
├── docs/                  # Documentation
├── setup.py              # Package installation
└── README.md             # Main documentation
```

