# Tutorial: Indexing 10 *E. coli* Assemblies

By the end you will have a queryable k-mer index of these assemblies built in
three commands:  
 [`design`](../commands/design.md) → [`build`](../commands/build.md) → [`query`](../commands/query.md).

---

## Prerequisites

- **kmhelpers** installed (see [Installation](../installation.md))
- Command `wget` to download the dataset
- ~200 MB of free disk space for the dataset + resulting index

### Dependencies

The following tools are installed alongside kmhelpers when using the conda environment:

- **[kmindex](https://github.com/tlemane/kmindex)** — the underlying indexing engine
- **[ntcard](https://github.com/BirolLab/ntCard)** — k-mer counter used by `list`

---

## Step 1 — Download the dataset

```bash
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
```

??? abstract "I/O"
    **Input:** 10 NCBI FTP URLs  
    **Output:** `coli_dataset/` 

---

## Step 2 — Create a file list

```bash
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
```

??? abstract "I/O"
    **Input:** paths to the 10 `.fna.gz` files (written manually)  
    **Output:** `coli_10.txt`

---

## Step 3 — Design the index ([`design`](../commands/design.md))

```bash
kmhelpers design coli_10.txt \
    -o coli_db/ \
    -n coli \
    -S initial \
    -k 25 \
    -b 1.1 \
    -g 2
```

??? abstract "I/O"
    **Input:** `coli_10.txt`  
    **Output:** `coli_db/list/` (JSONL), `coli_db/profile/` (profile.yaml, groups.png),
    `coli_db/compose/` (index definitions)

??? info "INFO"
    `design` runs [`list`](../commands/list.md) → [`profile`](../commands/profile.md) → [`compose`](../commands/compose.md) in a single command.  
    For a detailed walkthrough of each sub-command, see
    [Step-by-step: list → profile → compose](ecoli_steps.md#step-31-scan-samples-and-count-k-mers-list).

---

## Step 4 — Build the index ([`build`](../commands/build.md))

```bash
kmhelpers build coli_db/compose/coli/initial/coli.yaml -o coli_build/ --show-progress
```

??? abstract "I/O"
    **Input:** `coli_db/compose/coli/initial/coli.yaml`  
    **Output:** `coli_build/index.json` + sub-index data files in `coli_build/kmindex_data/` — ready-to-query index

??? info "INFO"
    `build` runs [`plan`](../commands/plan.md) → [`apply`](../commands/apply.md) in a single command, validating all paths before
    starting the build.  
    For a detailed walkthrough, or to run `plan` first and apply later with `bash`
    or `apply`, see [Step-by-step: plan → apply](ecoli_steps.md#step-41-preview-the-build-plan-plan).

---

## Step 5 — Query the index ([`query`](../commands/query.md))

Extract the first contig of the first sample as a query sequence:

```bash
zcat coli_dataset/GCA_000780515.1_ASM78051v1_genomic.fna.gz \
    | awk '/^>/{n++} n==2{exit} {print}' > query.fa
```

Then query the index:

```bash
kmhelpers query -r coli_build/ -o results/ query.fa
```

??? abstract "I/O"
    **Input:** `coli_build/` (index root), `query.fa` (first contig of `GCA_000780515`)  
    **Output:** `results/` 

??? success "RESULT"
    `query` writes one JSON file per sub-index into `results/query/result`:

    ??? tip "`coli_g0.json`"
        ```json
        {
            "coli_g0": {
                "JSPL01000060.1": {}
            }
        }
        ```

    ??? tip "`coli_g1.json`"
        ```json
        {
            "coli_g1": {
                "JSPL01000060.1": {
                    "GCA_000780515_1_ASM78051v1_genomic_fna": 1.0
                }
            }
        }
        ```

    Each value is the fraction of query k-mers found in that sample.
    `GCA_000780515` scores **1.0** -- a perfect match, as expected since `query.fa` was
    extracted from that assembly.

---

## References

- Jarno N. Alanko. (2022). *E. coli assemblies from NCBI* [Data set]. Zenodo. <https://doi.org/10.5281/zenodo.6577997>