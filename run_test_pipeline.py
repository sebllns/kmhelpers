#!/usr/bin/env python3
"""
Helper script to run the pytest pipeline with various configurations.
This replaces the shell script functionality with a Python interface.

Usage examples:
    python run_test_pipeline.py --tar tests/data/SYNTHETIC_ROD_10.tar --query tests/data/hum.fa
    python run_test_pipeline.py --input /path/to/existing/input --query tests/data/hum.fa
    python run_test_pipeline.py --tar tests/data/SYNTHETIC_ROD_10.tar --query tests/data/hum.fa --tmp ./custom_tmp --verbose
"""

import argparse
import sys
import os
import subprocess
from pathlib import Path

def run_pipeline(args):
    """Run the pytest pipeline with the given arguments."""
    
    # Validate inputs
    if not args.tar and not args.input:
        print("Error: Either --tar or --input must be provided")
        return 1
    
    if not args.query:
        print("Error: --query must be provided")
        return 1
    
    if args.tar and not os.path.exists(args.tar):
        print(f"Error: Tar archive '{args.tar}' not found")
        return 1
    
    if args.input and not os.path.exists(args.input):
        print(f"Error: Input directory '{args.input}' not found")
        return 1
    
    if not os.path.exists(args.query):
        print(f"Error: Query file '{args.query}' not found")
        return 1
    
    # Build pytest command
    pytest_cmd = [
        sys.executable, "-m", "pytest", 
        "test_pipeline.py",
        "-v"
    ]
    
    if args.verbose:
        pytest_cmd.append("-s")
    
    if args.stop_on_first_failure:
        pytest_cmd.append("-x")
    
    # Add custom options
    if args.tar:
        pytest_cmd.extend(["--tar_archive", args.tar])
    
    if args.input:
        pytest_cmd.extend(["--input_dir", args.input])
    
    pytest_cmd.extend(["--query", args.query])
    pytest_cmd.extend(["--tmp_dir", args.tmp])
    
    if args.capture == "no":
        pytest_cmd.append("--capture=no")
    
    # Add any additional pytest arguments
    if args.pytest_args:
        pytest_cmd.extend(args.pytest_args.split())
    
    print("Running pipeline with command:")
    print(" ".join(pytest_cmd))
    print("-" * 80)
    
    # Change to script directory
    script_dir = Path(__file__).parent
    os.chdir(script_dir)
    
    # Run pytest
    try:
        result = subprocess.run(pytest_cmd, check=False)
        return result.returncode
    except KeyboardInterrupt:
        print("\nPipeline interrupted by user")
        return 130
    except Exception as e:
        print(f"Error running pipeline: {e}")
        return 1


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run the genomic compression pipeline using pytest",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with tar archive
  python run_test_pipeline.py --tar tests/data/SYNTHETIC_ROD_10.tar --query tests/data/hum.fa
  
  # Run with existing input directory  
  python run_test_pipeline.py --input /path/to/input --query tests/data/hum.fa
  
  # Run with custom temporary directory
  python run_test_pipeline.py --tar tests/data/SYNTHETIC_ROD_10.tar --query tests/data/hum.fa --tmp ./my_tmp
  
  # Run with verbose output
  python run_test_pipeline.py --tar tests/data/SYNTHETIC_ROD_10.tar --query tests/data/hum.fa --verbose
  
  # Run specific test steps only
  python run_test_pipeline.py --tar tests/data/SYNTHETIC_ROD_10.tar --query tests/data/hum.fa --pytest-args "-k test_01_register"
        """
    )
    
    # Input sources (mutually exclusive)
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--tar", 
                            help="Path to tar archive containing test data")
    input_group.add_argument("--input", 
                            help="Path to existing input directory with registered index")
    
    # Required arguments
    parser.add_argument("--query", required=True,
                       help="Path to query file")
    
    # Optional arguments
    parser.add_argument("--tmp", default="./tmp",
                       help="Temporary directory path (default: ./tmp)")
    
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="Enable verbose output (includes print statements)")
    
    parser.add_argument("--stop-on-first-failure", "-x", action="store_true", 
                       help="Stop on first test failure")
    
    parser.add_argument("--capture", choices=["yes", "no"], default="yes",
                       help="Capture stdout/stderr (default: yes)")
    
    parser.add_argument("--pytest-args",
                       help="Additional arguments to pass to pytest (as a single quoted string)")
    
    # Parse arguments
    args = parser.parse_args()
    
    # Run pipeline
    exit_code = run_pipeline(args)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()