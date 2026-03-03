# kmhelpers Tests

This directory contains comprehensive unit tests for the kmhelpers package.

## Test Structure

- `test_index.py` - Unit tests for `KmtricksIndex` and `KmindexRegistry` classes

## Running Tests

### Run all tests
```bash
python -m pytest kmhelpers/tests/
```

### Run with verbose output
```bash
python -m pytest kmhelpers/tests/ -v
```

### Run specific test file
```bash
python -m pytest kmhelpers/tests/test_index.py
```

### Run specific test class
```bash
python -m pytest kmhelpers/tests/test_index.py::TestKmtricksIndexInitialization
```

### Run specific test method
```bash
python -m pytest kmhelpers/tests/test_index.py::TestKmtricksIndexInitialization::test_init_with_valid_index
```

### Run with coverage
```bash
python -m pytest kmhelpers/tests/ --cov=kmhelpers --cov-report=html
```

## Test Data

The tests use the `SYNTHETIC_ROD_10` index from `examples/data/`. If the directory doesn't exist, the tests will automatically extract it from the `.tar` archive.

## Test Coverage

### KmtricksIndex Tests (36 tests)
- **Initialization**: Tests for creating index objects with various parameters
- **Loading**: Tests for loading index properties from kmtricks files
- **Properties**: Tests for property management (get, set, import)
- **Matrix Operations**: Tests for matrix-related operations (paths, sizes, row counts)
- **Structure Check**: Tests for validating index structure
- **Copy/Move**: Tests for copying and moving indices to new locations
- **Iteration**: Tests for iterating over index partitions
- **String Representation**: Tests for `__str__` and `__repr__` methods

### KmindexRegistry Tests (22 tests)
- **Initialization**: Tests for creating registry objects
- **Index Management**: Tests for adding, removing, and checking indices
- **Properties**: Tests for getting index properties from registry
- **Iteration**: Tests for iterating over all indices in registry
- **Dictionary-like Access**: Tests for `__getitem__`, `__setitem__`, `__len__`
- **Path Operations**: Tests for getting index paths and checking directories

## Test Results

All 58 tests pass successfully:
- 36 tests for `KmtricksIndex`
- 22 tests for `KmindexRegistry`

## Requirements

The tests require:
- `pytest` for running tests
- `pytest-cov` (optional) for coverage reports
- `kmindex` binary in PATH for registry operations

## Notes

- Tests use temporary directories for all operations (cleaned up automatically)
- Each test is isolated and does not affect other tests
- The test data is copied to temporary locations to avoid modifying the original data
