#!/usr/bin/env python3
"""
Script to compress a selection of matrices from a kmtricks index.
"""

import argparse
import os
import subprocess
import sys
from kmhelpers.core.utils import Main, Kmindex
from kmhelpers.core.index import KmindexRegistry, KmtricksIndex


def main():

    parser = argparse.ArgumentParser(
        description="Create or update a kmindex registry from a folder containing many kmtricks indexes"
    )

    parser.add_argument(
        "-i",
        "--input-dir",
        help="Path to directory containing a set of kmtricks indexes",
    )

    parser.add_argument(
        "-o",
        "--output",
        default="kmindex-registry",
        help="Output kmindex registry (A new registry is created if the given path does not contain an existing registry)",
    )

    args = parser.parse_args()

    # Initialize kmhelpers environment
    print("Initializing kmhelpers...")

    script_dir = os.path.dirname(os.path.abspath(__file__))

    Main.init(os.path.join(script_dir, "bin"))

    print(Kmindex.version())

    # Configuration
    registry_path = args.output
    index_root = args.input_dir

    registry = KmindexRegistry(registry_path)

    # Loop over all directories in the data folder
    for index_id in os.listdir(index_root):
        entry_path = os.path.join(index_root, index_id)

        # Skip if not a directory or if it's the registry directory
        if not os.path.isdir(entry_path):
            continue

        try:
            # Load index
            index = KmtricksIndex(index_root, index_id)
            index.load_kmtricks_index()
            if index.check_structure():
                print(f"Found index: {index}")
                if registry.add_index(index):
                    print(f"Registered {index.index_id} in {registry.json_path}")
                else:
                    print(f"Index {index.index_id} already exists in registry")
        except Exception as e:
            print(f"Error processing {index_id}: {e}")
            continue

    print("---------------------------------------------------")
    print("Print registry:")
    print(registry)
    print("---------------------------------------------------")

    print("---------------------------------------------------")
    print("Iterate registry:")
    print(f"Available indices: {len(registry)} total")
    for idx in registry:
        print(f"  - {idx}")
    print("---------------------------------------------------")


if __name__ == "__main__":
    main()
