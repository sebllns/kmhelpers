# Migration Guide

This document explains the changes made during the restructuring of the kmhelpers project.

## What Changed

### Directory Structure

**Before:**
```
kmhelpers/
├── kmhelpers.py
├── index.py
├── compressor.py
├── compression_metrics.py
├── compress_index.py
├── query_index.py
└── register_index.py
```

**After:**
```
kmhelpers/
├── kmhelpers/
│   ├── __init__.py
│   ├── core/
│   │   ├── utils.py (formerly kmhelpers.py)
│   │   ├── index.py
│   │   └── __init__.py
│   ├── operations/
│   │   ├── compressor.py
│   │   └── __init__.py
│   ├── metrics/
│   │   ├── compression_metrics.py
│   │   └── __init__.py
│   └── cli/
│       ├── compress_index.py
│       ├── query_index.py
│       ├── register_index.py
│       └── __init__.py
├── examples/
├── tests/
├── docs/
├── setup.py
└── README.md
```

### Import Changes

#### Old Import Style
```python
import kmhelpers
from index import Index, IndexRegistry
from compressor import Compressor, CompressionParams
```

#### New Import Style (Recommended)
```python
# Use the main package imports
from kmhelpers import Main, Bin, Toolbox, Kmindex
from kmhelpers import Index, IndexRegistry
from kmhelpers import Compressor, CompressionParams
```

#### New Import Style (Alternative - Direct)
```python
# Or import directly from submodules
from kmhelpers.core.utils import Main, Bin, Toolbox, Kmindex
from kmhelpers.core.index import Index, IndexRegistry
from kmhelpers.operations.compressor import Compressor, CompressionParams
from kmhelpers.metrics.compression_metrics import PermutationData, CompressionData
```

### Code Fixes

1. **Removed duplicate imports** in kmhelpers.py:
   - `subprocess` was imported twice
   - `threading` was imported twice
   - Consolidated `typing` imports

2. **Removed duplicate class definition** in compression_metrics.py:
   - `CompressionData` was defined twice
   - Kept the more complete definition with Optional fields

### CLI Scripts

The CLI scripts are now accessible via:

```bash
# After installation with pip install -e .
kmhelpers-query --input /path --output /path --index ID --query file.fasta
kmhelpers-compress --input /path --output /path --index ID

# Or directly
python -m kmhelpers.cli.query_index ...
python -m kmhelpers.cli.compress_index ...
```

## Migration Steps

### For Library Users

1. **Update imports** in your code:
   ```python
   # Old
   import kmhelpers
   from index import Index

   # New
   from kmhelpers import Kmindex, Index
   ```

2. **No changes to function calls** - All APIs remain the same

### For CLI Users

1. **Install the package**:
   ```bash
   cd /path/to/kmhelpers
   pip install -e .
   ```

2. **Use new CLI commands** or module invocation:
   ```bash
   # Old
   python query_index.py --input ...

   # New (option 1)
   kmhelpers-query --input ...

   # New (option 2)
   python -m kmhelpers.cli.query_index --input ...
   ```

### For Developers

1. **Update imports** in your modules as shown above

2. **Follow new structure** for contributions:
   - Core utilities → `kmhelpers/core/`
   - Operations → `kmhelpers/operations/`
   - Metrics → `kmhelpers/metrics/`
   - CLI scripts → `kmhelpers/cli/`

3. **Run tests** (when available):
   ```bash
   pytest tests/
   ```

## Benefits of Restructuring

1. **Better Organization**: Clear separation of concerns
   - Core functionality
   - Operations/algorithms
   - Metrics/data structures
   - CLI tools

2. **Easier Imports**: Clean package-level imports
   ```python
   from kmhelpers import Index, Compressor, Kmindex
   ```

3. **Better Maintainability**:
   - Related code is grouped together
   - Easier to find and update code
   - Clear module boundaries

4. **Professional Structure**:
   - Follows Python packaging best practices
   - Ready for PyPI distribution
   - Proper `setup.py` for installation

5. **Documentation**:
   - Comprehensive README with examples
   - API reference
   - Migration guide

## Backward Compatibility

Most code should work with minimal changes:

- Function signatures unchanged
- Class APIs unchanged
- Only imports need updating

## Need Help?

If you encounter issues during migration:

1. Check the [README.md](../README.md) for updated examples
2. Look at [examples/basic_usage.py](../examples/basic_usage.py)
3. Verify your imports match the new structure
4. Check that `Main.init()` is called before using binary operations

## Quick Reference

### Common Import Patterns

```python
# Initialize
from kmhelpers import Main
Main.init()

# Working with indices
from kmhelpers import IndexRegistry, Index
registry = IndexRegistry("/path")
index = registry.get_index("my_index")

# Compression
from kmhelpers import Compressor, CompressionParams
compressor = Compressor()

# Direct utilities
from kmhelpers import Kmindex, Toolbox, Bin
```

### File Mapping

| Old File | New Location |
|----------|--------------|
| `kmhelpers.py` | `kmhelpers/core/utils.py` |
| `index.py` | `kmhelpers/core/index.py` |
| `compressor.py` | `kmhelpers/operations/compressor.py` |
| `compression_metrics.py` | `kmhelpers/metrics/compression_metrics.py` |
| `compress_index.py` | `kmhelpers/cli/compress_index.py` |
| `query_index.py` | `kmhelpers/cli/query_index.py` |
| `register_index.py` | `kmhelpers/cli/register_index.py` |
