#!/usr/bin/env python3
"""
Test script to generate bf_size for spans 1-36 using Python implementation.
"""

from pykmhelpers.core.bloom_filter import SpanManager

# Initialize with p=0.25
sm = SpanManager(p=0.25)

print("span bf_size")
print("---- -------")
for span in range(1, 37):
    bf_size = sm.get_bf_size(span)
    print(f"{span:2d}   {bf_size}")