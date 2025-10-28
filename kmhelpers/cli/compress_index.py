#!/usr/bin/env python3
import argparse
import json
import os
import shutil

from kmhelpers.core import utils as kmhelpers


def process_index(source_dir, output_dir, index_id):
    source_index_path = os.path.join(source_dir, index_id)

    assert os.path.isdir(
        source_index_path
    ), f"Source index path {source_index_path} is not a directory"

    source_dir=kmhelpers.Toolbox.get_canonical_path(source_dir)
    output_dir=kmhelpers.Toolbox.get_canonical_path(output_dir)

    output_data_dir = os.path.join(output_dir, "data")
    output_index_dir = os.path.join(output_data_dir, index_id)
    output_register_dir = os.path.join(output_dir, "register")
    

    print(f"Reordering index {index_id}...")
    print(f"Source index path: {source_index_path}")
    print(f"Output index path: {output_index_dir}")
    print(f"Output dir path: {output_dir}")
    print(f"Index ID: {index_id}")
    print(f"Input dir path: {source_dir}")

    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(output_data_dir, exist_ok=True)
    os.makedirs(output_register_dir, exist_ok=True)

    if not os.path.isfile(kmhelpers.Kmindex.get_json_path(output_register_dir)):
        kmhelpers.Kmindex.create_empty_index_json(output_register_dir)


    if os.path.exists(output_index_dir):
        print(
            f"Output index path {output_index_dir} already exists"
        )
        kmhelpers.Kmindex.register_index_in_json(output_data_dir, output_register_dir, index_id)
        return

    kmhelpers.Kmindex.check_index_structure(source_index_path)

    # Copy folder 
    shutil.copytree(
        source_index_path,
        output_index_dir
    )

    kmhelpers.Kmindex.register_index_in_json(output_data_dir, output_register_dir, index_id)

    # cmd_output = kmhelpers.BlockCompressorZSTD.compress_index(
    #     source_dir, output_data_dir, index_id
    # )



def main():

    raise DeprecationWarning("Deprecated... use Compressor class instead")

    parser = argparse.ArgumentParser(
        description="Reorder index")
    parser.add_argument(
        "--input", required=True, help="Input directory of data sources"
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output directory (where to put compressed index)",
    )
    parser.add_argument(
        "--index",
        nargs='+',  # one or more
        required=True,
        help="Folder(s) of the index to compress",
    )

    args = parser.parse_args()

    kmhelpers.Main.init()

    assert os.path.isdir(
        args.input), f"Input path {args.input} is not a directory"

    assert os.path.isdir(
        args.input), f"Input path {args.input} is not a directory"

    index_json_path = kmhelpers.Kmindex.get_json_path(args.input)
    assert os.path.isfile(
        index_json_path), f"JSON path {index_json_path} is not a file"
    index_ids = kmhelpers.Kmindex.read_index_ids_from_json(index_json_path)

    kmhelpers.Kmindex.validate_index_ids(args.index, index_ids)

    # Create output directory
    os.makedirs(args.output, exist_ok=True)
    assert os.path.isdir(
        args.output), f"Output path {args.output} is not a directory"
    assert os.access(
        args.output, os.W_OK
    ), f"Output directory {args.output} is not writable"

    for index_id in args.index:
        print(f"Processing index {index_id}...")
        process_index(args.input, args.output, index_id)


if __name__ == "__main__":
    main()
