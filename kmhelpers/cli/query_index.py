#!/usr/bin/env python3

import argparse
import json
import os

from kmhelpers.core import utils as kmhelpers


def main():
    parser = argparse.ArgumentParser(
        description="Helper script to register kmindex index in JSON file"
    )
    parser.add_argument(
        "--input", required=True, help="Input directory of data sources"
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output directory (where to create results)",
    )
    parser.add_argument(
        "--index",
        nargs="+",  # one or more
        required=True,
        help="ID(s) of the index to query from",
    )

    parser.add_argument(
        "--query",
        nargs="+",  # one or more
        required=True,
        help="Query file(s) in FASTA/FASTQ format",
    )

    parser.add_argument(
        "--zvalue", type=int, default=0, help="zvalue for kmindex (default: 0)"
    )

    parser.add_argument(
        "--threshold",
        type=float,
        default=0.0,
        help="threshold for kmindex (default: 0.0)",
    )

    parser.add_argument(
        "--compressed",
        action="store_true",
        help="Flag to use alternative kmindex version, for compressed indices",
    )

    parser.add_argument(
        "--report",
        required=False,
        default="report.json",
        help="Performance report filename, inside query output directory",
    )

    args = parser.parse_args()

    kmhelpers.Main.init()

    index_json_path = os.path.join(args.input, "index.json")
    # Validate input arguments
    assert os.path.isdir(args.input), f"Input path {args.input} is not a directory"

    assert os.path.isfile(index_json_path), f"JSON path {index_json_path} is not a file"
    assert os.access(
        index_json_path, os.R_OK
    ), f"JSON file {index_json_path} is not readable"
    index_ids = kmhelpers.Kmindex.read_index_ids_from_json(index_json_path)
    assert len(index_ids) > 0, f"No index IDs found in {index_json_path}"
    print(f"Found {len(index_ids)} index IDs in {index_json_path}")
    print(f"Index IDs: {', '.join(index_ids)}")

    kmhelpers.Kmindex.validate_index_ids(args.index, index_ids)

    os.makedirs(args.output, exist_ok=True)

    for query_file in args.query:
        assert os.path.isfile(query_file), f"Query file {query_file} is not a file"
        assert os.access(
            query_file, os.R_OK
        ), f"Query file {query_file} is not readable"
        print(f"Processing query file {query_file}...")

        query_output = os.path.join(
            args.output, os.path.splitext(os.path.basename(query_file))[0]
        )

        if os.path.isdir(query_output):
            print(f"Directory found: {query_output}. Skipping query...")
            continue

        result = kmhelpers.Kmindex.query_index(
            args.index,
            args.input,
            query_output,
            format="json",
            fastx=query_file,
            zvalue=args.zvalue,
            threshold=args.threshold,
            monitor=True,
            is_compressed=args.compressed,
        )

        if result is None:
            raise RuntimeError(f"Query command failed for {query_file}")

        km_output, km_monitor = result

        if not os.path.isdir(args.output):
            raise NotADirectoryError(f"Result directory not found: {query_output}")

        with open(os.path.join(query_output, ".cmd_output.log"), "w") as f:
            f.write(km_output)

        kmhelpers.Toolbox.save_to_json_file(
            km_monitor, os.path.join(query_output, args.report)
        )

        print(f"Query output: {query_output}")

        # print("kmindex output:")
        # print(km_output)

        # print("kmindex monitor:")
        # print(km_monitor)
        # print("----")


if __name__ == "__main__":
    main()
