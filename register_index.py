#!/usr/bin/env python3

import argparse
import json
import os
import kmhelpers

def main():
    parser = argparse.ArgumentParser(
        description="Helper script to register kmindex index in JSON file")
    parser.add_argument(
        "--input", required=True, help="Input directory of data sources"
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output directory (where to create json file and links)",
    )
    parser.add_argument(
    "--index",
    nargs='+',  # one or more
    required=True,
    help="Folder(s) of the index to register",
    )

    args = parser.parse_args()

    kmhelpers.Main.init()

    # Create output directory
    os.makedirs(args.output, exist_ok=True)
    
    index_json_path = kmhelpers.Kmindex.get_json_path(args.output)
    if not os.path.isfile(index_json_path):
        kmhelpers.Kmindex.create_empty_index_json(args.output)

    # Validate input arguments
    assert os.path.isdir(
        args.input), f"Input path {args.input} is not a directory"

    assert os.path.isfile(
        index_json_path), f"JSON path {index_json_path} is not a file"
    assert os.access(
        index_json_path, os.R_OK
    ), f"JSON file {index_json_path} is not readable"
    index_ids = kmhelpers.Kmindex.read_index_ids_from_json(index_json_path)


    assert os.path.isdir(
        args.output), f"Output path {args.output} is not a directory"
    assert os.access(
        args.output, os.W_OK
    ), f"Output directory {args.output} is not writable"

    for index_id in args.index:
        if(index_id in index_ids):
            print(f"Index {index_id} already registered, skipping...")
            continue
        print(f"Registering index {index_id}...")
        kmhelpers.Kmindex.register_index_in_json(
           args.input, args.output, index_id
        )


if __name__ == "__main__":
    main()
