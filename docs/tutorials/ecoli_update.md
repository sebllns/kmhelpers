# Update an existing index: [design](../commands/design.md) → [build](../commands/build.md)

This page is a companion to the [E. coli tutorial](ecoli.md). It shows how to add
samples to an index that already exists, without rebuilding it from scratch. It
assumes you have already followed the main steps and have `coli_db/` and
`coli_build/` on disk.

---

## Step 1 - Download a new sample

```bash
cd coli_dataset
wget "https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/000/005/845/GCA_000005845.2_ASM584v2/GCA_000005845.2_ASM584v2_genomic.fna.gz"
cd ..
```

??? abstract "I/O"
    **Input:** one NCBI FTP URL (*E. coli* K-12 MG1655 reference assembly)  
    **Output:** `coli_dataset/GCA_000005845.2_ASM584v2_genomic.fna.gz`

---

## Step 2 - Create a file list for the new samples

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

---

## Step 3 - Design the update session ([`design`](../commands/design.md))

Re-run `design` with the same `-o` and `-n` as
[Step 3](ecoli.md#step-3-design-the-index-design) of the tutorial, and a fresh
`-S` session ID:

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

---

## Step 4 - Build the update session ([`build`](../commands/build.md))

Build into the **same** `BUILD_DIR` as
[Step 4](ecoli.md#step-4-build-the-index-build) of the tutorial:

```bash
kmhelpers build coli_db/compose/coli/update/coli.yaml -o coli_build/ --show-progress
```

??? abstract "I/O"
    **Input:** `coli_db/compose/coli/update/coli.yaml`  
    **Output:** updated `coli_g0` in `coli_build/kmindex_data/update/coli_g0/`,
    previous version left in `coli_build/kmindex_data/initial/coli_g0/`,
    updated `coli_build/index.json`

??? info "INFO"
    Each session gets its own Bloom filter folder named after its `SESSION`
    directory, and is registered in `coli_build/index.json`. A given session can
    therefore be built only once into a given `BUILD_DIR`.

    Building a session into a `BUILD_DIR` that already holds the index triggers a
    merge. `kmindex` cannot add samples to an existing index in place, so the
    update merges the old and the new samples into a new index: `coli_g0` now
    holds its initial samples plus the new one and lives in
    `coli_build/kmindex_data/update/coli_g0/`. The files of the previous version
    are left in `coli_build/kmindex_data/initial/coli_g0/`, no longer registered.

    `GCA_000005845` falls in the span bucket of `coli_g0`, so only that
    sub-index is merged. `coli_g1` is untouched and stays in
    `coli_build/kmindex_data/initial/coli_g1/`.

??? warning "Disk space"
    The previous version and the updated one coexist on disk, during and after
    the merge. Plan for at least twice the size of the sub-indices being updated.

---

## Step 5 - Query the updated index ([`query`](../commands/query.md))

```bash
kmhelpers query -r coli_build/ -o results_update/ query.fa
```

??? success "RESULT"
    `coli_g0` now holds 6 samples, the 5 initial ones plus `GCA_000005845`.
    `query.fa` comes from `GCA_000780515`, indexed in `coli_g1`, which still
    scores **1.0**.

    The previous version is no longer registered, so the query reads only the
    updated index.

---

## Step 6 - Check the result and delete the previous version

The files of the previous version are kept, so the updated index can be
validated first. Once satisfied, delete them to reclaim the disk space:

```bash
# Registered indices and the samples they hold
kmhelpers manage -r coli_build/ list
kmhelpers manage -r coli_build/ info -n coli_g0

# Leftover files of the previous version of coli_g0
rm -rf coli_build/kmindex_data/initial/coli_g0
```

??? warning "WARNING"
    Delete the sub-index directory, not the whole `initial/` folder:
    `coli_build/kmindex_data/initial/coli_g1/` was not merged and is still in
    use by the registry.
