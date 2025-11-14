#!/bin/bash

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== kmhelpers examples ==="

# Step 1: Install kmhelpers in editable mode
echo ""
echo "Step 1: Installing kmhelpers package..."
pip install -e "$SCRIPT_DIR/.."

# Step 2: Extract the data archive
echo ""
echo "Step 2: Extracting SYNTHETIC_ROD_10.tar..."
cd "$SCRIPT_DIR/data"
if [ -f "SYNTHETIC_ROD_10.tar" ]; then
    tar -xf SYNTHETIC_ROD_10.tar
    echo "Archive extracted successfully"
else
    echo "Warning: SYNTHETIC_ROD_10.tar not found in $SCRIPT_DIR/data"
fi
cd "$SCRIPT_DIR"

# Step 3: Run the examples in order
echo ""
echo "Step 3: Running examples..."

echo ""
echo "--- Running create_registry.py ---"
python3 "$SCRIPT_DIR/create_registry.py"

echo ""
echo "--- Running browsing_registry.py ---"
python3 "$SCRIPT_DIR/browsing_registry.py" "$SCRIPT_DIR/data/registry"

echo ""
echo "--- Running compress_selection.py ---"
python3 "$SCRIPT_DIR/compress_selection.py"

echo ""
echo "=== Setup and examples completed successfully ==="
