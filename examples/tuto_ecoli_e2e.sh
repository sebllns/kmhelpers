#!/usr/bin/env bash
# E. coli tutorial, end to end: https://sebllns.github.io/kmhelpers/tutorials/ecoli/
set -euo pipefail

DOC=https://sebllns.github.io/kmhelpers

# Working directory: first argument, or a fresh temporary directory
workdir="${1:-$(mktemp -d)}"
mkdir -p "$workdir" && cd "$workdir"
echo "Working directory: $PWD"

echo "== Step 1: download the dataset =="
mkdir -p coli_dataset && cd coli_dataset
wget "https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/000/780/515/GCA_000780515.1_ASM78051v1/GCA_000780515.1_ASM78051v1_genomic.fna.gz"
wget "https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/001/076/125/GCA_001076125.1_ASM107612v1/GCA_001076125.1_ASM107612v1_genomic.fna.gz"
wget "https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/001/417/575/GCA_001417575.1_ASM141757v1/GCA_001417575.1_ASM141757v1_genomic.fna.gz"
wget "https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/000/944/435/GCA_000944435.1_Ec57A_E8C1_MIRA_assembly/GCA_000944435.1_Ec57A_E8C1_MIRA_assembly_genomic.fna.gz"
wget "https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/001/075/925/GCA_001075925.1_ASM107592v1/GCA_001075925.1_ASM107592v1_genomic.fna.gz"
wget "https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/000/936/715/GCA_000936715.1_E8C1_assembly/GCA_000936715.1_E8C1_assembly_genomic.fna.gz"
wget "https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/000/939/215/GCA_000939215.1_Ec57A_A7_MIRA_assembly/GCA_000939215.1_Ec57A_A7_MIRA_assembly_genomic.fna.gz"
wget "https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/001/413/795/GCA_001413795.1_ASM141379v1/GCA_001413795.1_ASM141379v1_genomic.fna.gz"
wget "https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/001/373/195/GCA_001373195.1_57A_A7_assembly/GCA_001373195.1_57A_A7_assembly_genomic.fna.gz"
wget "https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/000/938/575/GCA_000938575.1_D1C4_assembly/GCA_000938575.1_D1C4_assembly_genomic.fna.gz"
cd ..

echo "== Step 2: design the index =="
# Sharding is disabled (--sb 0): each group is one index, coli_g0 and coli_g1. With a
# shard budget, a group of many or large samples is split into independent shards
# (coli_g0_p0, coli_g0_p1, ...), so that no index grows without limit; for 10
# assemblies it is not needed. See https://sebllns.github.io/kmhelpers/commands/compose/#description (Sharding).
kmhelpers design coli_dataset \
    -o coli_db/ \
    -n coli \
    -s initial \
    -k 25 \
    -b 1.1 \
    -g 2 \
    --sb 0

echo "== Step 3: build the index =="
# Chunking is disabled (--cb 0): each shard is built by one kmtricks run. With a chunk
# budget (or a low open-files limit), the samples of a shard are built in several runs
# (chunks), then merged; on a cluster, chunks can run on several nodes at once. See
# https://sebllns.github.io/kmhelpers/commands/build/#shards-and-chunks.
#
# Here the build runs on this machine. On a SLURM cluster, the same build is planned for
# the jobs of a cluster file, submitted, and followed:
#   kmhelpers build coli_db -o coli_build/ --hpc cluster.yaml --notify you@example.com
#   kmhelpers apply coli_db -o coli_build/ --status --sp
# See https://sebllns.github.io/kmhelpers/commands/build/#on-a-cluster and https://sebllns.github.io/kmhelpers/commands/plan/#cluster.
kmhelpers build coli_db -o coli_build/ --cb 0 --show-progress

echo "== Step 4: query the index =="
zcat coli_dataset/GCA_000780515.1_ASM78051v1_genomic.fna.gz \
    | awk '/^>/{n++} n<2' > query.fa

kmhelpers query -r coli_build/ -o results/ query.fa

echo "== Update step 1: download a new sample =="
cd coli_dataset
wget "https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/000/005/845/GCA_000005845.2_ASM584v2/GCA_000005845.2_ASM584v2_genomic.fna.gz"
cd ..

echo "== Update step 2: create the file list for the new samples =="
cat > coli_update.txt << 'EOF'
coli_dataset/GCA_000005845.2_ASM584v2_genomic.fna.gz
EOF

echo "== Update step 3: design the update session =="
kmhelpers design coli_update.txt -o coli_db/ -n coli -s update

echo "== Update step 4: build the update session =="
kmhelpers build coli_db -s update -o coli_build/ --cb 0 --show-progress

echo "== Update step 5: query the updated index =="
kmhelpers query -r coli_build/ -o results_update/ query.fa

echo "== Update step 6: check the updated index =="
kmhelpers manage -r coli_build/ list
kmhelpers manage -r coli_build/ info --sh coli_g0

echo "The update merged the new sample into its shard, in place: the previous version is"
echo "deleted once the new one is checked (kept in coli_build/work/update/previous/ with"
echo "--keep-previous). See $DOC/commands/build/#updating-an-index"
