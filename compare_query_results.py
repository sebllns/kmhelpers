#!/usr/bin/env python3
import argparse
import kmhelpers
import os


def main():
    parser = argparse.ArgumentParser(
        description='Parse and compare query results')
    parser.add_argument(
        'ground_truth', help='Path to the directory containing ground truth results')
    parser.add_argument(
        'results', help='Path to the directory containing results to compare')
    parser.add_argument(
        'query', help='Query ID to compare')
    parser.add_argument(
        "index",
        nargs='+',  # one or more
        help="ID(s) to compare results",
    )
    parser.add_argument("--check", action="store_true", 
                        default=True,
                        help="Enable check mode")

    args = parser.parse_args()

    for index_id in args.index:
        print(f"Processing index {index_id}...")
        query_eq, monitor = kmhelpers.Kmindex.compare_query_result_dir(os.path.join(
            args.ground_truth, args.query), os.path.join(args.results, args.query), index_id)
        if not query_eq:
            print(f"Query results are different for {index_id}")
            print(f"Ground truth path: {args.ground_truth}")
            print(f"Results path: {args.results}")
            if args.check:
                raise Exception("FATAL: results not equal")
        print("Performances diff:")
        print(monitor)


if __name__ == "__main__":
    main()
