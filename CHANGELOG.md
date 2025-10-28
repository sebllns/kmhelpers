# Changelog

All notable changes to this project will be documented in this file.

## [0.0.1] - 2025-10-28

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

