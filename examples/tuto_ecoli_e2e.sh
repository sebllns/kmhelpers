#!/usr/bin/env bash

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

