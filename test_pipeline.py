#!/usr/bin/env python3
"""
Pytest-based test pipeline that replaces the shell script pipeline.
Converts run_compress_pipeline.sh into a comprehensive test suite.

Usage:
    pytest test_pipeline.py --tar_archive=tests/data/SYNTHETIC_ROD_10.tar --query=tests/data/hum.fa
    pytest test_pipeline.py --input_dir=/path/to/input --query=tests/data/hum.fa
    pytest test_pipeline.py --tmp_dir=./custom_tmp --tar_archive=tests/data/SYNTHETIC_ROD_10.tar --query=tests/data/hum.fa
"""

import pytest
import os
import sys
import shutil
import tarfile
import tempfile
import subprocess
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add scripts directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import kmhelpers
    import query_index
    import register_index
    import compress_index
    import reorder_index
    import compare_query_results
except ImportError as e:
    pytest.skip(f"Required modules not available: {e}", allow_module_level=True)


class TestPipelineConfig:
    """Configuration and setup for the test pipeline."""
    
    @classmethod
    def create(cls, tar_archive=None, input_dir=None, query=None, tmp_dir="./tmp"):
        """Create and configure a TestPipelineConfig instance."""
        config = cls()
        config.tar_archive = tar_archive
        config.input_dir = input_dir
        config.query = query
        config.tmp_dir = tmp_dir
        config.index_id = None
        config.setup_paths()
        return config
        
    def setup_paths(self):
        """Set up all necessary paths for the pipeline."""
        if self.tar_archive:
            self.index_id = os.path.splitext(os.path.basename(self.tar_archive))[0]
            self.input_dir = os.path.join(self.tmp_dir, self.index_id, "input")
        else:
            self.index_id = os.path.basename(self.input_dir.rstrip('/'))
        
        self.output_dir = os.path.join(self.tmp_dir, self.index_id, "output")
        self.register_dir = os.path.join(self.input_dir, "register")
        self.data_dir = os.path.join(self.input_dir, "data")
    
    @property
    def query_basename_no_ext(self):
        """Get query filename without extension for comparison script."""
        return os.path.splitext(os.path.basename(self.query))[0]


@pytest.fixture(scope="session")
def pipeline_config(request):
    """Session-scoped fixture for pipeline configuration."""
    tar_archive = request.config.getoption("--tar_archive", default=None)
    input_dir = request.config.getoption("--input_dir", default=None) 
    query = request.config.getoption("--query", default=None)
    tmp_dir = request.config.getoption("--tmp_dir", default="./tmp")
    
    if not tar_archive and not input_dir:
        pytest.skip("Either --tar_archive or --input_dir must be provided")
    
    if not query:
        pytest.skip("--query must be provided")
    
    config = TestPipelineConfig.create(tar_archive, input_dir, query, tmp_dir)
    return config


@pytest.fixture(scope="session", autouse=True)
def setup_pipeline(pipeline_config):
    """Set up the test environment and extract data if needed."""
    config = pipeline_config
    
    # Initialize kmhelpers with correct bin path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    bin_path = os.path.join(script_dir, "..", "bin")
    os.environ["KMHELPERS_BIN_PATH"] = os.path.abspath(bin_path)
    kmhelpers.Main.init()
    
    # Clean up existing directories
    if os.path.exists(config.output_dir):
        shutil.rmtree(config.output_dir)
    
    if config.tar_archive:
        if os.path.exists(config.input_dir):
            shutil.rmtree(config.input_dir)
        
        # Create directories
        os.makedirs(config.data_dir, exist_ok=True)
        os.makedirs(config.register_dir, exist_ok=True)
        os.makedirs(config.output_dir, exist_ok=True)
        
        # Extract tar archive
        print(f"Extracting {config.tar_archive} to {config.data_dir}...")
        with tarfile.open(config.tar_archive, 'r') as tar:
            tar.extractall(config.data_dir, filter='data')
        
        # Verify extraction
        extracted_path = os.path.join(config.data_dir, config.index_id)
        if not os.path.exists(extracted_path):
            pytest.fail(f"Extracted directory {extracted_path} not found")
    
    else:
        # Using existing input directory
        os.makedirs(config.output_dir, exist_ok=True)
        if not os.path.exists(config.input_dir):
            pytest.fail(f"Input directory {config.input_dir} does not exist")
    
    # Verify query file exists
    if not os.path.exists(config.query):
        pytest.fail(f"Query file {config.query} not found")
    
    yield config
    
    # Cleanup (optional - comment out for debugging)
    # if os.path.exists(config.tmp_dir):
    #     shutil.rmtree(config.tmp_dir)


class TestCompressionPipeline:
    """Main test class for the compression pipeline."""

    def test_01_register_index(self, setup_pipeline):
        """Step 1: Register the index from extracted data."""
        config = setup_pipeline
        
        if config.tar_archive:
            # Run register_index.py equivalent
            input_path = config.data_dir
            output_path = config.register_dir
        else:
            # For existing directory, assume it's already registered or copy structure
            input_path = config.input_dir
            output_path = config.register_dir
            os.makedirs(output_path, exist_ok=True)
        
        # Call register_index functionality
        with patch('sys.argv', ['register_index.py', '--input', input_path, 
                               '--output', output_path, '--index', config.index_id]):
            try:
                register_index.main()
                print(f"✅ Index {config.index_id} registered successfully")
            except SystemExit as e:
                if e.code != 0:
                    pytest.fail(f"Index registration failed with code {e.code}")
        
        # Verify registration created index.json
        index_json = os.path.join(output_path, "index.json")
        assert os.path.exists(index_json), f"index.json not found at {index_json}"
        
        # Verify index exists in JSON
        assert kmhelpers.Kmindex.index_exists_in_json(index_json, config.index_id), \
            f"Index {config.index_id} not found in {index_json}"

    def test_02_query_original_index(self, setup_pipeline):
        """Step 2: Query original index - baseline performance measurement."""
        config = setup_pipeline
        
        original_result_dir = os.path.join(config.output_dir, "results", "original")
        os.makedirs(original_result_dir, exist_ok=True)
        
        with patch('sys.argv', ['query_index.py', '--input', config.register_dir,
                               '--output', original_result_dir, '--index', config.index_id,
                               '--query', config.query]):
            try:
                query_index.main()
                print(f"✅ Original index queried successfully")
            except SystemExit as e:
                if e.code != 0:
                    pytest.fail(f"Original index query failed with code {e.code}")
        
        # Verify results were created (look in subdirectories)
        result_files = list(Path(original_result_dir).glob("**/*.json"))
        assert len(result_files) > 0, f"No result files found in {original_result_dir}"

    def test_03_compress_original_index(self, setup_pipeline):
        """Step 3: Compress original index."""
        config = setup_pipeline
        
        compress_output_dir = os.path.join(config.output_dir, "index_compressed")
        
        with patch('sys.argv', ['compress_index.py', '--input', config.register_dir,
                               '--output', compress_output_dir, '--index', config.index_id]):
            try:
                compress_index.main()
                print(f"✅ Index compressed successfully")
            except SystemExit as e:
                if e.code != 0:
                    pytest.fail(f"Index compression failed with code {e.code}")
        
        # Verify compressed index was created
        compressed_register = os.path.join(compress_output_dir, "register")
        assert os.path.exists(compressed_register), f"Compressed register not found at {compressed_register}"

    def test_04_query_compressed_index(self, setup_pipeline):
        """Step 4: Query compressed index and test performance."""
        config = setup_pipeline
        
        compressed_result_dir = os.path.join(config.output_dir, "results", "compressed")
        os.makedirs(compressed_result_dir, exist_ok=True)
        compressed_register = os.path.join(config.output_dir, "index_compressed", "register")
        
        with patch('sys.argv', ['query_index.py', '--input', compressed_register,
                               '--output', compressed_result_dir, '--index', config.index_id,
                               '--query', config.query, '--compressed']):
            try:
                query_index.main()
                print(f"✅ Compressed index queried successfully")
            except SystemExit as e:
                if e.code != 0:
                    pytest.fail(f"Compressed index query failed with code {e.code}")
        
        # Verify results were created (look in subdirectories)
        result_files = list(Path(compressed_result_dir).glob("**/*.json"))
        assert len(result_files) > 0, f"No result files found in {compressed_result_dir}"

    def test_05_compare_original_vs_compressed(self, setup_pipeline):
        """Step 5: Compare original vs compressed results using compare_query_results.py."""
        config = setup_pipeline
        
        original_result_dir = os.path.join(config.output_dir, "results", "original")
        compressed_result_dir = os.path.join(config.output_dir, "results", "compressed")
        
        # Use compare_query_results.py with proper arguments
        with patch('sys.argv', ['compare_query_results.py', original_result_dir, 
                               compressed_result_dir, config.query_basename_no_ext, 
                               config.index_id]):
            try:
                compare_query_results.main()
                print(f"✅ Original vs Compressed results comparison completed")
            except SystemExit as e:
                if e.code != 0:
                    pytest.fail(f"Results comparison failed with code {e.code}")

    def test_06_reorder_index(self, setup_pipeline):
        """Step 6: Reorder index for optimization."""
        config = setup_pipeline
        
        reorder_output_dir = os.path.join(config.output_dir, "index_reordered")
        
        with patch('sys.argv', ['reorder_index.py', '--input', config.register_dir,
                               '--output', reorder_output_dir, '--index', config.index_id]):
            try:
                reorder_index.main()
                print(f"✅ Index reordered successfully")
            except SystemExit as e:
                if e.code != 0:
                    pytest.fail(f"Index reordering failed with code {e.code}")
        
        # Verify reordered index was created
        reordered_register = os.path.join(reorder_output_dir, "register")
        assert os.path.exists(reordered_register), f"Reordered register not found at {reordered_register}"

    def test_07_query_reordered_index(self, setup_pipeline):
        """Step 7: Query reordered index."""
        config = setup_pipeline
        
        reordered_result_dir = os.path.join(config.output_dir, "results", "reordered")
        os.makedirs(reordered_result_dir, exist_ok=True)
        reordered_register = os.path.join(config.output_dir, "index_reordered", "register")
        
        with patch('sys.argv', ['query_index.py', '--input', reordered_register,
                               '--output', reordered_result_dir, '--index', config.index_id,
                               '--query', config.query]):
            try:
                query_index.main()
                print(f"✅ Reordered index queried successfully")
            except SystemExit as e:
                if e.code != 0:
                    pytest.fail(f"Reordered index query failed with code {e.code}")
        
        # Verify results were created (look in subdirectories)
        result_files = list(Path(reordered_result_dir).glob("**/*.json"))
        assert len(result_files) > 0, f"No result files found in {reordered_result_dir}"

    def test_08_compare_original_vs_reordered(self, setup_pipeline):
        """Step 8: Compare original vs reordered results using compare_query_results.py."""
        config = setup_pipeline
        
        original_result_dir = os.path.join(config.output_dir, "results", "original")
        reordered_result_dir = os.path.join(config.output_dir, "results", "reordered")
        
        # Use compare_query_results.py with proper arguments
        with patch('sys.argv', ['compare_query_results.py', original_result_dir,
                               reordered_result_dir, config.query_basename_no_ext,
                               config.index_id]):
            try:
                compare_query_results.main()
                print(f"✅ Original vs Reordered results comparison completed")
            except SystemExit as e:
                if e.code != 0:
                    pytest.fail(f"Results comparison failed with code {e.code}")

    def test_09_compress_reordered_index(self, setup_pipeline):
        """Step 9: Compress reordered index - final optimized version."""
        config = setup_pipeline
        
        reordered_register = os.path.join(config.output_dir, "index_reordered", "register")
        final_output_dir = os.path.join(config.output_dir, "index_reordered_compressed")
        
        with patch('sys.argv', ['compress_index.py', '--input', reordered_register,
                               '--output', final_output_dir, '--index', config.index_id]):
            try:
                compress_index.main()
                print(f"✅ Reordered index compressed successfully")
            except SystemExit as e:
                if e.code != 0:
                    pytest.fail(f"Reordered index compression failed with code {e.code}")
        
        # Verify final compressed index was created
        final_register = os.path.join(final_output_dir, "register")
        assert os.path.exists(final_register), f"Final register not found at {final_register}"

    def test_10_query_final_compressed_index(self, setup_pipeline):
        """Step 10: Query final compressed+reordered index."""
        config = setup_pipeline
        
        final_result_dir = os.path.join(config.output_dir, "results", "reordered_compressed")
        os.makedirs(final_result_dir, exist_ok=True)
        final_register = os.path.join(config.output_dir, "index_reordered_compressed", "register")
        
        with patch('sys.argv', ['query_index.py', '--input', final_register,
                               '--output', final_result_dir, '--index', config.index_id,
                               '--query', config.query, '--compressed']):
            try:
                query_index.main()
                print(f"✅ Final compressed index queried successfully")
            except SystemExit as e:
                if e.code != 0:
                    pytest.fail(f"Final index query failed with code {e.code}")
        
        # Verify results were created (look in subdirectories)
        result_files = list(Path(final_result_dir).glob("**/*.json"))
        assert len(result_files) > 0, f"No result files found in {final_result_dir}"

    def test_11_compare_original_vs_final(self, setup_pipeline):
        """Step 11: Compare original vs final optimized results using compare_query_results.py."""
        config = setup_pipeline
        
        original_result_dir = os.path.join(config.output_dir, "results", "original")
        final_result_dir = os.path.join(config.output_dir, "results", "reordered_compressed")
        
        # Use compare_query_results.py with proper arguments
        with patch('sys.argv', ['compare_query_results.py', original_result_dir,
                               final_result_dir, config.query_basename_no_ext,
                               config.index_id]):
            try:
                compare_query_results.main()
                print(f"✅ Original vs Final results comparison completed")
            except SystemExit as e:
                if e.code != 0:
                    pytest.fail(f"Results comparison failed with code {e.code}")

    def test_12_analyze_compression_ratios(self, setup_pipeline):
        """Step 12: Analyze matrix sizes and compression ratios."""
        config = setup_pipeline
        
        # Collect size information from all index variants
        folders = [
            config.register_dir,
            os.path.join(config.output_dir, "index_compressed", "register"),
            os.path.join(config.output_dir, "index_reordered", "register"),
            os.path.join(config.output_dir, "index_reordered_compressed", "register"),
        ]
        
        folder_types = ["original", "compressed", "reordered", "reordered_compressed"]
        
        # Use Kmindex.compare_matrices_size functionality
        size_analysis = kmhelpers.Kmindex.compare_matrices_size(
            folders, folder_types, config.index_id)
        
        print("✅ Compression analysis completed")
        
        # Save analysis results
        analysis_file = os.path.join(config.output_dir, "size_analysis.json")
        kmhelpers.Toolbox.save_to_json_file(size_analysis, analysis_file)
        
        assert os.path.exists(analysis_file), "Size analysis file not created"
            
    def test_13_generate_pipeline_report(self, setup_pipeline):
        """Step 13: Generate final pipeline execution report."""
        config = setup_pipeline
        
        report = {
            "pipeline_execution": {
                "index_id": config.index_id,
                "query_file": config.query,
                "query_basename_no_ext": config.query_basename_no_ext,
                "input_dir": config.input_dir,
                "output_dir": config.output_dir,
                "steps_completed": [
                    "register_index",
                    "query_original", 
                    "compress_original",
                    "query_compressed",
                    "compare_original_compressed",
                    "reorder_index",
                    "query_reordered",
                    "compare_original_reordered", 
                    "compress_reordered",
                    "query_final",
                    "compare_original_final",
                    "analyze_compression"
                ]
            },
            "result_directories": {
                "original": os.path.join(config.output_dir, "results", "original"),
                "compressed": os.path.join(config.output_dir, "results", "compressed"),
                "reordered": os.path.join(config.output_dir, "results", "reordered"),
                "final": os.path.join(config.output_dir, "results", "reordered_compressed")
            },
            "index_directories": {
                "original": config.register_dir,
                "compressed": os.path.join(config.output_dir, "index_compressed", "register"),
                "reordered": os.path.join(config.output_dir, "index_reordered", "register"),
                "final": os.path.join(config.output_dir, "index_reordered_compressed", "register")
            }
        }
        
        report_file = os.path.join(config.output_dir, "pipeline_report.json")
        kmhelpers.Toolbox.save_to_json_file(report, report_file)
        
        assert os.path.exists(report_file), "Pipeline report not created"
        print(f"✅ Pipeline completed successfully! Report: {report_file}")


if __name__ == '__main__':
    # Run pytest with this file
    pytest.main([__file__, "-v", "-s"])