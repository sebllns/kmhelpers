#!/bin/sh
# Run a freshly built ntcard on a tiny plain and gzipped FASTA and check the
# k-mer count. The gzipped case exercises the fopen hook used for decompression.
set -eu
ntcard="$1"
dir="$(mktemp -d)"
printf '>test\nAAAAAAAAAAGGGGGGGGTCCCTGGGGGGGGGGGCCCCCCCCTTTGCCCAAAAAAAA\n' > "$dir/sample"
gzip -k "$dir/sample"
for f in "$dir/sample" "$dir/sample.gz"; do
  "$ntcard" -t 2 -k 25 -o "$dir/hist" "$f" 2>&1 | tee "$dir/log"
  grep -qE 'k=25[[:space:]]+F1[[:space:]]+33$' "$dir/log"
done
rm -rf "$dir"
