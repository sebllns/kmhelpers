#!/usr/bin/env bash
set -euo pipefail

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

echo "== Step 2: create the file list =="
cat > coli_10.txt << 'EOF'
coli_dataset/GCA_000780515.1_ASM78051v1_genomic.fna.gz
coli_dataset/GCA_001076125.1_ASM107612v1_genomic.fna.gz
coli_dataset/GCA_001417575.1_ASM141757v1_genomic.fna.gz
coli_dataset/GCA_000944435.1_Ec57A_E8C1_MIRA_assembly_genomic.fna.gz
coli_dataset/GCA_001075925.1_ASM107592v1_genomic.fna.gz
coli_dataset/GCA_000936715.1_E8C1_assembly_genomic.fna.gz
coli_dataset/GCA_000939215.1_Ec57A_A7_MIRA_assembly_genomic.fna.gz
coli_dataset/GCA_001413795.1_ASM141379v1_genomic.fna.gz
coli_dataset/GCA_001373195.1_57A_A7_assembly_genomic.fna.gz
coli_dataset/GCA_000938575.1_D1C4_assembly_genomic.fna.gz
EOF

echo "== Step 3: design the index =="
kmhelpers design coli_10.txt \
    -o coli_db/ \
    -n coli \
    -S initial \
    -k 25 \
    -b 1.1 \
    -g 2

echo "== Step 4: build the index =="
kmhelpers build coli_db/compose/coli/initial/coli.yaml -o coli_build/ --show-progress

echo "== Step 5: query the index =="
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
kmhelpers design coli_update.txt -o coli_db/ -n coli -S update

echo "== Update step 4: build the update session =="
kmhelpers build coli_db/compose/coli/update/coli.yaml -o coli_build/ --show-progress

echo "== Update step 5: query the updated index =="
kmhelpers query -r coli_build/ -o results_update/ query.fa

echo "== Update step 6: check the updated index =="
kmhelpers manage -r coli_build/ list
kmhelpers manage -r coli_build/ info -n coli_g0

echo "The files of the previous version are unregistered from index, but kept on disk, until deleted:"
echo "rm -rf coli_build/kmindex_data/initial/coli_g0"
