
## Going Further

### Build an index with [`apply`](../commands/apply.md)

```bash
kmhelpers apply coli3682_db/index.yaml -o coli3682_db/ -t 8
```

`apply` runs the build. The `-t 8` flag sets the number of threads; adjust it
to match your machine.

Useful options for long runs:

```bash
# Show a progress bar
kmhelpers apply coli3682_db/index.yaml -o coli3682_db/ -t 8 --show-progress

# Abort immediately on any error
kmhelpers apply coli3682_db/index.yaml -o coli3682_db/ -t 8 --fail-fast

# Get an email when the build finishes
kmhelpers apply coli3682_db/index.yaml -o coli3682_db/ -t 8 \
    --notify you@example.com
```

Once complete, the index is registered in `coli3682_db/` and ready to query.

### Query the index with advanced options ([`query`](../commands/query.md))

Results are written in JSON by default. Use `-f` to change the format:

```bash
# CSV output
kmhelpers query -r coli3682_build/ -o results/ -f csv query.fa

# Print results to the console as well
kmhelpers query -r coli3682_build/ -n index -o results/ -p query.fa
```

To query all sequences together as a single batch (one result row instead of
one per sequence):

```bash
kmhelpers query -r coli3682_db/ -n index -o results/ \
    --single-query my_batch query.fa
```

Use `-R` to filter out low-confidence hits (fraction of shared k-mers below
the threshold):

```bash
kmhelpers query -r coli3682_db/ -n index -o results/ -R 0.5 query.fa
```

### Update the index with new samples

Add samples to the index built in the tutorial, without rebuilding it from
scratch.

#### Step 1 - Download a new sample

```bash
cd coli_dataset
wget "https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/000/005/845/GCA_000005845.2_ASM584v2/GCA_000005845.2_ASM584v2_genomic.fna.gz"
cd ..
```

??? abstract "I/O"
    **Input:** one NCBI FTP URL (*E. coli* K-12 MG1655 reference assembly)  
    **Output:** `coli_dataset/GCA_000005845.2_ASM584v2_genomic.fna.gz`

#### Step 2 - Create a file list for the new samples

```bash
cat > coli_update.txt << 'EOF'
coli_dataset/GCA_000005845.2_ASM584v2_genomic.fna.gz
EOF
```

??? abstract "I/O"
    **Input:** path to the new `.fna.gz` file  
    **Output:** `coli_update.txt`

??? info "INFO"
    List only the **new** samples. Samples already indexed must **not** be repeated.

#### Step 3 - Design the update session ([`design`](../commands/design.md))

Re-run `design` with the same `-o` and `-n` as the tutorial, and a fresh `-S`
session ID:

```bash
kmhelpers design coli_update.txt -o coli_db/ -n coli -S update
```

??? abstract "I/O"
    **Input:** `coli_update.txt`, existing layout `coli_db/compose/coli_layout.yaml`  
    **Output:** `coli_db/compose/coli/update/coli.yaml`

??? info "INFO"
    `design` detects the existing layout file at `coli_db/compose/coli_layout.yaml`,
    skips the [`profile`](../commands/profile.md) step, and composes only the new
    samples. The k-mer size, span base and grouping of the initial run are reused,
    so the new sub-indices stay compatible with the existing ones.

#### Step 4 - Build the update session ([`build`](../commands/build.md))

Build into the **same** `BUILD_DIR` as the initial run:

```bash
kmhelpers build coli_db/compose/coli/update/coli.yaml -o coli_build/ --show-progress
```

??? abstract "I/O"
    **Input:** `coli_db/compose/coli/update/coli.yaml`  
    **Output:** `coli_build/kmindex_data/update/`, updated `coli_build/index.json`

??? info "INFO"
    Each session gets its own Bloom filter folder named after its `SESSION`
    directory, and is registered in `coli_build/index.json`. A given session can
    therefore be built only once into a given `BUILD_DIR`.

#### Step 5 - Query the updated index ([`query`](../commands/query.md))

```bash
kmhelpers query -r coli_build/ -o results_update/ query.fa
```

??? success "RESULT"
    The results now include the sub-indices of the `update` session alongside
    the initial ones. `query.fa` comes from `GCA_000780515`, so the new sample
    scores low while `GCA_000780515` still scores **1.0**.

---

### Next steps

- **Compress** the index to save disk space:
  ```bash
  kmhelpers compress -r coli3682_db/ -n index --reorder
  ```
- See the [Command Reference](../commands/index.md) for the full option list of
  every command used here.


### 3682

This tutorial walks through the full kmhelpers workflow on a real public dataset:
3 682 *E. coli* assemblies downloaded from NCBI and archived on Zenodo.

> Jarno N. Alanko. (2022). * E. coli assemblies from NCBI* [Data set].
> Zenodo. <https://doi.org/10.5281/zenodo.6577997>