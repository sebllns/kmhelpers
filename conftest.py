"""
Pytest configuration file for the compression pipeline tests.
"""

def pytest_addoption(parser):
    """Add custom command line options for pytest."""
    parser.addoption("--tar_archive", action="store", default="tests/data/SYNTHETIC_ROD_10.tar",
                     help="Path to tar archive containing test data")
    parser.addoption("--input_dir", action="store", default=None, 
                     help="Path to existing input directory")
    parser.addoption("--query", action="store", default="tests/data/hum.fa",
                     help="Path to query file")
    parser.addoption("--tmp_dir", action="store", default="./tmp",
                     help="Temporary directory path (default: ./tmp)")