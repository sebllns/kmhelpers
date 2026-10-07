#!/usr/bin/env bash
# Mini end-to-end example on random data:
#   design -> build -> query -> update -> query
# Requires kmhelpers, kmindex and ntcard on PATH.
set -euo pipefail

# Fixed seed so the random samples are reproducible (read by every kmhelpers call)
export KMHELPERS_SEED="${KMHELPERS_SEED:-42}"

# Working directory: first argument, or a fresh temporary directory
workdir="${1:-$(mktemp -d)}"
mkdir -p "$workdir" && cd "$workdir"
echo "Working directory: $PWD"

# 1. Generate 10 small random samples -> data/data_0.fasta .. data_9.fasta
kmhelpers test create-fasta -o data -n 10 -a 3000 -m 2500

# 2. Design (list -> profile -> compose) and build the initial index
kmhelpers design data \
    -o db/ \
    -n idx \
    -S initial \
    -k 21 \
    -b 1.1 \
    -g 1

kmhelpers build db/compose/idx/initial/idx.yaml -o build/

# 3. Query a whole indexed sample: it should score 1.0 against itself
kmhelpers query -r build/ -o results/ -f json data/data_0.fasta
cat results/data_0/results.json

# 4. Update: one new, slightly smaller sample (must fit an existing span
#    bucket), listed then composed against the existing layout (no -pf)
kmhelpers test create-fasta -o update -n 1 -a 2000 -m 1800
kmhelpers list update -o db/list/upd.jsonl -k 21
kmhelpers compose db/list/upd.jsonl -o db/compose -n idx -S upd

kmhelpers build db/compose/idx/upd/idx.yaml -o build/

# 5. The new sample is queryable, and the original still matches
kmhelpers query -r build/ -o results_upd/ -f json update/update_0.fasta
cat results_upd/update_0/results.json

kmhelpers query -r build/ -o results_after/ -f json data/data_0.fasta
cat results_after/data_0/results.json

# 6. Compressed queries: gz read by kmindex, bz2/xz/zst decompressed first,
#    all should give the same result as the plain file
#    (formats whose tool is not installed are skipped)
compress() {
    local tool=$1 ext=$2
    shift 2
    if command -v "$tool" > /dev/null; then
        "$@"
    else
        echo "Skipping .$ext: $tool not found" >&2
    fi
}

mkdir -p compressed
src=data/data_0.fasta
dst=compressed/data_0.fasta
compress gzip gz sh -c "gzip -c $src > $dst.gz"
compress bzip2 bz2 sh -c "bzip2 -c $src > $dst.bz2"
compress xz xz sh -c "xz -c $src > $dst.xz"
compress zstd zst zstd -q -o "$dst.zst" "$src"
compress zip zip zip -qj "$dst.zip" "$src"

for ext in gz bz2 xz zst; do
    [ -f "$dst.$ext" ] || continue
    kmhelpers query -r build/ -o "results_$ext/" -f json "$dst.$ext"
    cat "results_$ext/data_0/results.json"
done

# Compressed input from stdin
if [ -f "$dst.gz" ]; then
    kmhelpers query -r build/ -o results_stdin/ -f json - < "$dst.gz"
    cat results_stdin/*/results.json
fi

# zip is rejected
if [ -f "$dst.zip" ]; then
    if kmhelpers query -r build/ -o results_zip/ -f json "$dst.zip"; then
        echo "Error: zip query should have failed" >&2
        exit 1
    fi
    echo "zip rejected as expected"
fi

# 7. Query formats: the same sequence as FASTA/FASTQ, plain or gz
mkdir -p formats
awk '/^>/ { if (seq) exit; next } { seq = seq $0 }
     END { print "@q"; print seq; print "+"; gsub(/./, "I", seq); print seq }' \
    "$src" > formats/q_fastq.fastq
awk '/^>/ { if (n++) exit } { print }' "$src" > formats/q_fasta.fasta
cp formats/q_fasta.fasta formats/q_fa.fa
cp formats/q_fastq.fastq formats/q_fq.fq
gzip -c formats/q_fa.fa > formats/q_fa_gz.fa.gz
gzip -c formats/q_fq.fq > formats/q_fq_gz.fq.gz

for f in formats/*; do
    stem=$(basename "${f%%.*}")
    kmhelpers query -r build/ -o "results_$stem/" -f json "$f"
    cat "results_$stem/$stem/results.json"
done

# Reads shorter than s+z (here 21+6=27) are rejected
printf '@short\nACGTACGTACGTACGTACGT\n+\nIIIIIIIIIIIIIIIIIIII\n' | gzip > short.fq.gz
if kmhelpers query -r build/ -o results_short/ -f json short.fq.gz; then
    echo "Error: query with reads shorter than s+z should have failed" >&2
    exit 1
fi
echo "short reads rejected as expected"
# info.yaml is kept on failure, with the error and the kmindex output
cat results_short/short/info.yaml