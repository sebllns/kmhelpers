#!/usr/bin/env bash
# Large-scale planning example on a fake sample list (no sequence data):
#   create-list (300K samples) -> design -> plan --offline
# Shows how a 300K-sample collection is split into sub-indexes, and the
# build scripts plan would export for a cluster node. Nothing is built.
# Requires kmhelpers on PATH (kmindex is only used to read its version).
set -euo pipefail

# Working directory: first argument, or a fresh temporary directory
workdir="${1:-$(mktemp -d)}"
mkdir -p "$workdir" && cd "$workdir"
echo "Working directory: $PWD"

# Resource limits of the target build node: 64 GB RAM, 65536 open files
# (ulimit -n), 32 threads. Used by plan to size threads/partitions and to
# split builds whose samples do not fit the open-files limit.
LIMITS='{"ram": 64000000000, "files": 65536, "threads": 32}'

# Number of storage-balanced groups the spans are gathered into
NB_GROUPS=5

# Shard budget: about how many k-mers a shard holds, summed over its samples.
# A group holding more is split into independent shards (here 13 of up to
# ~100GB each). 0 for no limit: one index per group.
SHARD_BUDGET='2**38'

# 1. Fake manifest of 300K bacterial-like assemblies: median 5M distinct
#    25-mers, spread of 1 span. Only the JSONL is written, no FASTA.
mkdir -p db/list
kmhelpers test create-list \
    -o db/list/bact.jsonl \
    -n 300000 \
    -k 25 \
    --mu 5000000 \
    --sd 1 \
    -p bact \
    --seed 42

# 2. Design from the JSONL (the list step is skipped): profile spans, then
#    compose the index definitions
kmhelpers design db/list/bact.jsonl \
    -o db/ \
    -n bact \
    -s initial \
    -k 25 \
    -g "$NB_GROUPS" \
    --sb "$SHARD_BUDGET"

# 3. Plan offline: sample files are not checked (they do not exist), and
#    the plan and the scripts of every shard are written to build/assets/initial/
kmhelpers plan db \
    -o build/ \
    --offline \
    --limits "$LIMITS"

# 4. What plan produced
echo
echo "Shards: $(ls -d build/assets/initial/*/ | wc -l)"
echo "kmtricks runs: $(ls build/assets/initial/*/*.sh | grep -vc '/publish.sh$')"
echo "kmindex merge commands: $(grep -ho 'kmindex merge' build/assets/initial/*/publish.sh | wc -l)"
echo "Plan: build/assets/initial/plan.yaml (run it with: kmhelpers apply db -o build/)"
echo "Plan report: $(ls build/logs/kmhelpers_plan_*.yaml)"
