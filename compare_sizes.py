#!/usr/bin/env python3
import json
import argparse
import os
from datetime import datetime
import kmhelpers

def process_entry(entry, index, directory):
    """
    Process a single entry from the benchmark bundle.
    Add your custom logic here.
    """
    print(f"\n--- Processing Entry {index + 1} ---")
    print(f"Index Path: {entry['index_path']}")
    print(f"Type: {entry['type']}")
    print(f"Source: {entry['source']}")
    print(f"Added On: {entry['added_on']}")
    
    # Add your processing logic here
    # For example:
    # - Run benchmarks on the index
    # - Copy files
    # - Generate reports
    # - etc.
    
    # Example of additional processing based on type
    if entry['type'] == 'kmtricks':
        print("  → Processing kmtricks index...")
    elif entry['type'] == 'reordered':
        print("  → Processing reordered index...")
    elif entry['type'] == 'compressed':
        print("  → Processing compressed index...")
    elif entry['type'] == 'reordered_compressed':
        print("  → Processing reordered+compressed index...")
    else:
        print(f"  → Processing {entry['type']} index...")
    
    # Return True if processing succeeded, False otherwise
    return True

def parse_benchmark_bundle(json_path, index_id, partition_count):
    """
    Parse the benchmark bundle JSON and process each entry.
    """
    if not os.path.exists(json_path):
        print(f"Error: File {json_path} not found!")
        return False
    
    try:
        with open(json_path, 'r') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {json_path}: {e}")
        return False
    
    if not isinstance(data, list):
        print("Error: JSON should contain a list of entries")
        return False
    
    print(f"Found {len(data)} entries in {json_path}")
    
    folders = [entry['index_path'] for entry in data if 'index_path' in entry]
    types = [entry['type'] for entry in data if 'type' in entry]
    result = kmhelpers.Kmindex.compare_matrices_size(folders, types, index_id, partition_count)
    
    # Or write pretty JSON to file
    with open('matrix_comparison.json', 'w') as f:
        json.dump(result, f, indent=2)
    
def main():
    parser = argparse.ArgumentParser(description='Parse and process benchmark bundle JSON file')
    parser.add_argument('json_path', help='Path to the benchmark bundle JSON file')
    parser.add_argument('index_id', help='Index identifier for processing')
    parser.add_argument('partition_count', help='Number of partitions to consider', type=int)

    args = parser.parse_args()

    parse_benchmark_bundle(args.json_path, args.index_id, args.partition_count)

if __name__ == "__main__":
    main()
