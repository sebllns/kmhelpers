#!/usr/bin/env python3
"""
Script to compress a selection of matrices from a kmtricks index.
"""

import argparse
import os
import subprocess
import sys
from kmhelpers.core.utils import Main, Bin, Toolbox
from kmhelpers.core.index import KmtricksIndex
from kmhelpers.operations.compressor import Compressor, CompressionParams

def main():

    short_hash = subprocess.check_output(['git', 'rev-parse', '--short=7', 'HEAD']).decode('ascii').strip()
    print(f"commit={short_hash}")

    # Initialize kmhelpers environment
    print("Initializing kmhelpers...")

    script_dir = os.path.dirname(os.path.abspath(__file__))

    Main.init(default_bin_path=os.path.join(script_dir, "bin"))

    Bin.fetch(
        Bin.reorderer(),
        Toolbox.get_canonical_path(
            os.path.join(
                script_dir, "../../BitmatrixShuffle/build/main_bitmatrixshuffle"
            )
        ),
    )

    Bin.fetch(
        Bin.compressor(),
        Toolbox.get_canonical_path(
            os.path.join(
                script_dir, "../../BlockCompressor/build/block_compressor_bin"
            )
        ),
    )

    Bin.fetch(
        Bin.decompressor(),
        Toolbox.get_canonical_path(
            os.path.join(
                script_dir, "../../BlockCompressor/build/block_decompressor_bin"
            )
        ),
    )

    # Configuration
    index_root = os.path.join(script_dir, "data")
    index_id = "SYNTHETIC_ROD_10"

    ref_matrix = 1  # Reference matrix partition number
    matrix_list = [7, 12, 123]  # List of matrix partitions to compress

    # Compression parameters
    params = CompressionParams(
        block_size=8388608,
        group_size=0,
        subsample_size=20000,
        threshold=0,
        enable_check=True,
        enable_overwrite=True,
    )

    # Load index
    idx = KmtricksIndex(index_root, index_id)
    idx.load_kmtricks_index()

    # Compress selection
    compressor = Compressor(enable_metrics=True)
    # compressor.compress_index_selection(params, idx, ref_matrix, matrix_list)
    # print(f"Inplace compression completed for index {index_id}")

    compressor.compress_index_selection(
        params, idx, ref_matrix, matrix_list, os.path.join(index_root, f"compression/{index_id}_c{short_hash}_b{params.block_size}_g{params.group_size}_s{params.subsample_size}_t{params.threshold}")
    )
    print(f"External compression completed for index {index_id}")

if __name__ == "__main__":
    main()
