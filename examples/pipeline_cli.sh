#!/usr/bin/env bash
#
# End-to-end kmhelpers pipeline via the CLI.
#
# Mirrors pykmhelpers/tests/test_pipeline_e2e.py (TestDesignBuildQueryUpdateQuery):
#   design -> build -> query -> update -> query
#
# Random FASTA is generated with `kmhelpers test create-fasta`. Queries feed a
# whole indexed sample back as the query, so it scores ~1.0.
#
# Requires: kmhelpers, kmindex and ntcard on PATH.

set -euo pipefail

KMER_SIZE=21
MIN_SCORE=0.9

export KMHELPERS_LOG_LEVEL=4
export KMHELPERS_SEED=42

workdir="examples_cli"
rm -rf "$workdir"
mkdir -p "$workdir"
cd "$workdir"
echo "Working directory: $workdir"

# Fail if a query result does not contain the expected sample at MIN_SCORE.
check_hit() {
    local results_dir="$1" sample="$2"
    kmhelpers results "$results_dir" --check "$sample" --min-score "$MIN_SCORE"
}

# 1. Generate 5 samples -> data/data_0.fasta .. data_4.fasta (names data_0..).
kmhelpers test create-fasta -o data -n 5 -a 3000 -m 2500

# 2. Design (list -> profile -> compose), scanning the data/ directory.
kmhelpers design data -o db -n idx -S initial -k "$KMER_SIZE" -b 1.1 -g 1

# 3. Build (plan -> apply).
kmhelpers build db/compose/idx/initial/idx.yaml -o build

# 4. Query a sample against its own index -> perfect hit.
kmhelpers query data/data_0.fasta -r build -o results -f json
check_hit results data_0

# 5. Update: a new, smaller sample in a separate dir (distinct name update_0),
#    composed against the existing layout (no -pf) and rebuilt in place.
kmhelpers test create-fasta -o update -n 1 -a 2000 -m 1800
mkdir -p db/list
kmhelpers list update -o db/list/upd.jsonl -k "$KMER_SIZE"
kmhelpers compose db/list/upd.jsonl -o db/compose -n idx -S upd
kmhelpers build db/compose/idx/upd/idx.yaml -o build

# 6. The new sample is queryable, and the original still matches.
kmhelpers query update/update_0.fasta -r build -o results_upd -f json
check_hit results_upd update_0

kmhelpers query data/data_0.fasta -r build -o results_after -f json
check_hit results_after data_0

kmhelpers query data/data_0.fasta -r build -o results_md -f md


echo "All queries matched. Pipeline complete."