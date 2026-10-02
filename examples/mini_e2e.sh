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