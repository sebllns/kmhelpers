#!/usr/bin/env bash
# Large-scale planning example on a fake sample list (no sequence data):
#   create-list (200K samples) -> design -> plan --offline
# Shows how a 200K-sample collection is split into sub-indexes, and the
# build scripts plan would export for a cluster node. Nothing is built.
# Requires kmhelpers on PATH (kmindex is only used to read its version).
set -euo pipefail

# Working directory: first argument, or a fresh temporary directory
workdir="${1:-$(mktemp -d)}"
mkdir -p "$workdir" && cd "$workdir"
echo "Working directory: $PWD"

# Resource limits of the target build node: 128 GB RAM, 65536 open files
# (ulimit -n), 32 threads. Used by plan to size threads/partitions and to
# split builds whose samples do not fit the open-files limit.
LIMITS='{"ram": 128000000000, "files": 65536, "threads": 32}'

# Number of storage-balanced groups the spans are gathered into
NB_GROUPS=10

# Maximum size of one shard: a span holding more is split into independent
# shards. Empty for a single unlimited index per span.
SHARD_SIZE=20GB

# 1. Fake manifest of 200K bacterial-like assemblies: median 5M distinct
#    31-mers, spread of 1 span. Only the JSONL is written, no FASTA.
mkdir -p db/list
kmhelpers test create-list \
    -o db/list/bact.jsonl \
    -n 200000 \
    -k 31 \
    -mu 5000000 \
    -sd 1 \
    -p bact \
    --seed 42

# 2. Design from the JSONL (the list step is skipped): profile spans, then
#    compose the index definitions
kmhelpers design db/list/bact.jsonl \
    -o db/ \
    -n bact \
    -S initial \
    -k 25 \
    -g "$NB_GROUPS" \
    ${SHARD_SIZE:+-si "$SHARD_SIZE"}

# 3. Plan offline: sample files are not checked (they do not exist), and
#    the build scripts are written to build/assets/
kmhelpers plan db/compose/bact/initial/bact.yaml \
    -o build/ \
    --offline \
    --limits "$LIMITS"

# 4. What plan produced
echo
echo "Sub-index scripts: $(ls build/assets/*.sh | grep -vc kmhelpers_apply.sh)"
echo "kmindex build commands: $(grep -h '^kmindex build' build/assets/*.sh | wc -l)"
echo "kmindex merge commands: $(grep -h '^kmindex merge' build/assets/*.sh | wc -l)"
echo "Runner: build/assets/kmhelpers_apply.sh"
echo "Plan report: $(ls build/logs/kmhelpers_plan_*.yaml)"
