#!/usr/bin/env python3
"""
Script to compress a selection of matrices from a kmtricks index.
"""

import argparse
import os
import subprocess
import sys
from kmhelpers.core.utils import Main
from kmhelpers.core.index import KmindexRegistry, KmtricksIndex

def main():

    # short_hash = subprocess.check_output(['git', 'rev-parse', '--short=7', 'HEAD']).decode('ascii').strip()
    # print(f"commit={short_hash}") 

    # Initialize kmhelpers environment
    print("Initializing kmhelpers...")

    script_dir = os.path.dirname(os.path.abspath(__file__))

    Main.init(os.path.join(script_dir, "bin"))

    # Configuration
    index_root = os.path.join(script_dir, "data")
    index_id = "SYNTHETIC_ROD_10" 

    # Load index
    index = KmtricksIndex(index_root, index_id)
    index.load_kmtricks_index()
    print(str(index))
    index.check_structure()

    registry = KmindexRegistry(os.path.join(index_root, "registry"))

    if registry.add_index(index):
        print(f"Registred {index.index_id} in {registry.json_path}")

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
