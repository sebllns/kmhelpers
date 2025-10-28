#!/usr/bin/env python3
"""
Test script for the Index class.
"""

import sys
import os

# Add the scripts directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from index import Index, IndexRegistry
from kmhelpers import Main

def test_index_registry():
    """Test IndexRegistry functionality."""
    print("=== Testing IndexRegistry ===")
    
    # Test with existing index.json
    registry_path = "/home/sbelleno/work/git/compression/compression-pipeline/input/indices/SYNTHETIC_ROD"
    
    try:
        registry = IndexRegistry(registry_path)
        print(f"✓ IndexRegistry created: {registry}")
        
        # List indices
        indices = registry.list_indices()
        print(f"✓ Available indices: {indices}")
        
        # Test iteration
        print("✓ Iterating over indices:")
        for idx in registry:
            print(f"  - {idx}")
            
    except Exception as e:
        print(f"✗ IndexRegistry test failed: {e}")
        return False
    
    return True

def test_index_class():
    """Test Index class functionality."""
    print("\n=== Testing Index Class ===")
    
    # Test with existing index
    root_path = "/home/sbelleno/work/git/compression/compression-pipeline/input/indices/SYNTHETIC_ROD"
    index_id = "SYNTHETIC_ROD_10"
    
    try:
        # Create Index object
        index = Index(root_path, index_id)
        print(f"✓ Index created: {index}")
        
        # Test basic properties
        print(f"✓ Samples: {index.nb_samples}")
        print(f"✓ Partitions: {index.nb_partitions}")
        print(f"✓ Sample names: {index.samples}")
        print(f"✓ K-mer size: {index.smer_size}")
        print(f"✓ Bloom size: {index.bloom_size}")
        print(f"✓ SHA1: {index.sha1}")
        
        # Test computed properties
        print(f"✓ Bytes per row: {index.bytes_per_row}")
        print(f"✓ Header size: {index.header_size}")
        
        # Test path methods
        print(f"✓ Index path: {index.path}")
        print(f"✓ Matrices path: {index.matrices_path}")
        
        # Test matrix operations (if matrices exist)
        if os.path.exists(index.matrices_path):
            print("✓ Testing matrix operations:")
            matrix_path = index.get_matrix_path(0)
            print(f"  - Matrix 0 path: {matrix_path}")
            
            if os.path.exists(matrix_path):
                matrix_size = index.get_matrix_byte_size(0)
                row_count = index.get_matrix_row_count(0)
                print(f"  - Matrix 0 size: {matrix_size} bytes")
                print(f"  - Matrix 0 rows: {row_count}")
            else:
                print(f"  - Matrix file doesn't exist: {matrix_path}")
        
        # Test structure check
        structure_ok = index.check_structure()
        print(f"✓ Structure check: {'PASS' if structure_ok else 'FAIL'}")
        
        # Test property access
        all_props = index.get_all_properties()
        print(f"✓ All properties: {list(all_props.keys())}")
        
        # Test specific property access
        bloom_size = index.get_property("bloom_size")
        print(f"✓ Bloom size via get_property: {bloom_size}")
        
    except Exception as e:
        print(f"✗ Index test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

def test_error_handling():
    """Test error handling."""
    print("\n=== Testing Error Handling ===")
    
    try:
        # Test non-existent directory
        try:
            Index("/nonexistent/path", "test")
            print("✗ Should have failed for non-existent path")
            return False
        except FileNotFoundError:
            print("✓ Correctly handled non-existent path")
        
        # Test non-existent index ID
        try:
            Index("/home/sbelleno/work/git/compression/compression-pipeline/input/indices/SYNTHETIC_ROD", "NONEXISTENT")
            print("✗ Should have failed for non-existent index ID")
            return False
        except KeyError:
            print("✓ Correctly handled non-existent index ID")
        
        # Test non-existent property
        index = Index("/home/sbelleno/work/git/compression/compression-pipeline/input/indices/SYNTHETIC_ROD", "SYNTHETIC_ROD_10")
        try:
            index.get_property("nonexistent_property")
            print("✗ Should have failed for non-existent property")
            return False
        except KeyError:
            print("✓ Correctly handled non-existent property")
            
    except Exception as e:
        print(f"✗ Error handling test failed: {e}")
        return False
    
    return True

def main():
    """Run all tests."""
    print("Starting Index class tests...\n")
    
    # Initialize kmhelpers
    Main.init()
    
    # Run tests
    tests = [
        test_index_registry,
        test_index_class,
        test_error_handling
    ]
    
    results = []
    for test in tests:
        results.append(test())
    
    # Summary
    print(f"\n=== Test Summary ===")
    passed = sum(results)
    total = len(results)
    print(f"Tests passed: {passed}/{total}")
    
    if passed == total:
        print("🎉 All tests passed!")
        return 0
    else:
        print("❌ Some tests failed!")
        return 1

if __name__ == "__main__":
    sys.exit(main())