#!/usr/bin/env python3
"""
Basic usage example for kmhelpers.

This example demonstrates:
1. Initializing the environment
2. Loading an index registry
3. Accessing index properties
4. Basic operations
"""

from kmhelpers import Main, IndexRegistry

def main():
    # Initialize kmhelpers environment
    print("Initializing kmhelpers...")
    Main.init()

    # Example: Working with an index registry
    # Replace with your actual index path
    index_path = "/path/to/your/indices"

    try:
        # Load the index registry
        registry = IndexRegistry(index_path)

        # List all available indices
        print(f"\nAvailable indices: {len(registry)} total")
        for index_id in registry.list_indices():
            print(f"  - {index_id}")

        # Get a specific index (replace with your index ID)
        if len(registry) > 0:
            index_id = registry.list_indices()[0]
            index = registry.get_index(index_id)

            # Display index information
            print(f"\nIndex Information:")
            print(f"  ID: {index.index_id}")
            print(f"  Samples: {index.nb_samples}")
            print(f"  Partitions: {index.nb_partitions}")
            print(f"  K-mer size: {index.smer_size}")
            print(f"  Minimizer size: {index.minim_size}")
            print(f"  Bytes per row: {index.bytes_per_row}")

            # Get matrix information for first partition
            if index.nb_partitions > 0:
                partition = 0
                matrix_path = index.get_matrix_path(partition)
                matrix_size = index.get_matrix_byte_size(partition)
                row_count = index.get_matrix_row_count(partition)

                print(f"\nPartition {partition} Information:")
                print(f"  Path: {matrix_path}")
                print(f"  Size: {matrix_size:,} bytes")
                print(f"  Rows: {row_count:,}")
                print(f"  Elements: {row_count * index.nb_samples:,}")

    except FileNotFoundError as e:
        print(f"\nError: {e}")
        print("Please update the 'index_path' variable with your actual index directory.")
    except Exception as e:
        print(f"\nUnexpected error: {e}")

if __name__ == "__main__":
    main()
