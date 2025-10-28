#!/usr/bin/env python3
import json
import argparse
from datetime import datetime
import os
from kmhelpers import Toolbox

def add_to_benchmark_bundle(index_path, entry_type, source, output_path):
    """
    Add an entry to the benchmark bundle JSON file.
    If the file exists, append to it. If not, create it.
    """
    # Create the new entry
    new_entry = {
        "index_path": Toolbox.get_canonical_path(index_path),
        "type": entry_type,
        "source": source,
        "added_on": datetime.now().isoformat() + "Z"
    }
    
    # Try to load existing data
    data = []
    if os.path.exists(output_path):
        try:
            with open(output_path, 'r') as f:
                data = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            print(f"Warning: Could not read existing file {output_path}. Creating new file.")
            data = []
    
    # Append the new entry
    data.append(new_entry)
    
    # Write back to file
    with open(output_path, 'w') as f:
        json.dump(data, f, indent=4)
    
    print(f"Added entry to {output_path}")
    print(f"Entry: {json.dumps(new_entry, indent=2)}")

def main():
    parser = argparse.ArgumentParser(description='Add entries to benchmark bundle JSON file')
    parser.add_argument('index_path', help='Path to the index')
    parser.add_argument('type', help='Type of the entry (e.g., kmtricks, reordered, compressed)')
    parser.add_argument('source', help='Source of the entry')
    parser.add_argument('output_path', help='Output path for the JSON file')
    
    args = parser.parse_args()
    
    add_to_benchmark_bundle(args.index_path, args.type, args.source, args.output_path)

if __name__ == "__main__":
    main()
