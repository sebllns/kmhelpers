# kmhelpers Tests

This directory contains comprehensive unit tests for the kmhelpers package.

## Test Structure

### Unit tests (no external binaries)
- `test_index.py` - Unit tests for `KmtricksIndex` and `KmindexRegistry` classes
- `test_imports.py` - Smoke tests that every public class imports correctly
- `test_bf_sizes.py` - Unit tests for `SpanManager` and `BloomFilterSpecs` sizing helpers
- `test_byte.py` - Unit tests for `ByteCounter` and the `SizeFormat`/`SizeUnit` enums

### Integration tests (require external binaries)
- `test_pipeline_e2e.py` - End-to-end CLI pipeline tests. Each command runs in a
  fresh subprocess (`python -m pykmhelpers.cli.kmhelpers`) and shells out to
  `kmindex` and `ntcard`, which **must be installed and reachable** (guaranteed
  in CI — there are no skip guards). Two flows are covered:
  `design → build → query → update → query` and the decomposed
  `list → profile → compose` / `plan → apply`, plus negative tests asserting
  that failure paths exit non-zero.

## Running Tests

### Run all tests
```bash
python -m pytest pykmhelpers/tests/
```

### Run with verbose output
```bash
python -m pytest pykmhelpers/tests/ -v
```

### Run specific test file
```bash
python -m pytest pykmhelpers/tests/test_index.py
```

### Run specific test class
```bash
python -m pytest pykmhelpers/tests/test_index.py::TestKmtricksIndexInitialization
```

### Run specific test method
```bash
python -m pytest pykmhelpers/tests/test_index.py::TestKmtricksIndexInitialization::test_init_with_valid_index
```

### Run with coverage
```bash
python -m pytest pykmhelpers/tests/ --cov=pykmhelpers --cov-report=html
```

## Test Data

The tests use the `SYNTHETIC_ROD_10` index from `examples/data/`. If the directory doesn't exist, the tests will automatically extract it from the `.tar` archive.

## Test Coverage

### KmtricksIndex Tests
- **Initialization**: Tests for creating index objects with various parameters
- **Loading**: Tests for loading index properties from kmtricks files
- **Properties**: Tests for property management (get, set, import)
- **Matrix Operations**: Tests for matrix-related operations (paths, sizes, row counts)
- **Structure Check**: Tests for validating index structure
- **Copy/Move**: Tests for copying and moving indices to new locations
- **Iteration**: Tests for iterating over index partitions
- **String Representation**: Tests for `__str__` and `__repr__` methods
- **v0.6.3 parameters**: `auto_load` on `KmtricksIndex`

### KmindexRegistry Tests
- **Initialization**: Tests for creating registry objects
- **Index Management**: Tests for adding, removing, and checking indices
- **Properties**: Tests for getting index properties from registry
- **Iteration**: Tests for iterating over all indices in registry
- **Dictionary-like Access**: Tests for `__getitem__`, `__setitem__`, `__len__`
- **Path Operations**: Tests for getting index paths and checking directories
- **v0.6.3 parameters**: `auto_create`, and `remove_index` with `delete_files`/`skip_unregistered`

### Import Tests (`test_imports.py`)
Smoke tests that every public class is importable from its submodule, from the
`core`/`operations` packages, and from the top-level `pykmhelpers` package.

### Bloom Filter Tests (`test_bf_sizes.py`)
Unit tests for `SpanManager` (bf_size golden values, the `b` base parameter,
`dispatch`/`min_kmer_count`/`max_kmer_count` round-trips) and the matrix cost
helpers (`kmindex_matrix_bit_count`, `kmindex_matrix_storage_cost`,
`BloomFilterSpecs.matrix_size`).

## Requirements

The tests require:
- `pytest` for running tests
- `pytest-cov` (optional) for coverage reports
- `kmindex` binary in PATH for registry operations

## Notes

- Tests use temporary directories for all operations (cleaned up automatically)
- Each test is isolated and does not affect other tests
- The test data is copied to temporary locations to avoid modifying the original data
