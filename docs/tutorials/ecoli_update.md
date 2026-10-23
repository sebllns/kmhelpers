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
`-s` session ID:

```bash
kmhelpers design coli_update.txt -o coli_db/ -n coli -s update
```

??? abstract "I/O"
    **Input:** `coli_update.txt`, existing layout `coli_db/compose/coli/layout.yaml`  
    **Output:** `coli_db/compose/coli/update/index.yaml`

??? info "INFO"
    `design` detects the existing layout file at `coli_db/compose/coli/layout.yaml`,
    skips the [`profile`](../commands/profile.md) step, and composes only the new
    samples. The k-mer size, span base and grouping of the initial run are reused,
    so the new sub-indices stay compatible with the existing ones.

---

## Step 4 - Build the update session ([`build`](../commands/build.md))

Build into the **same** `BUILD_DIR` as
[Step 4](ecoli.md#step-4-build-the-index-build) of the tutorial:

```bash
kmhelpers build coli_db -s update -o coli_build/ --cb 0 --show-progress
```

??? abstract "I/O"
    **Input:** `coli_db/compose/coli/update/index.yaml`  
    **Output:** updated `coli_g0` in `coli_build/coli_g0/`, updated
    `coli_build/index.json`

??? info "INFO"
    Each index keeps its folder, `coli_build/<name>/`. While the session is
    built, its runs and merges live in `coli_build/work/update/`, deleted at the
    end. Building the same session again resumes it, or does nothing if it
    finished.

    Building a session into a `BUILD_DIR` that already holds the index triggers a
    merge. `kmindex` cannot add samples to an existing index in place, so the
    update merges the old and the new samples into a new index, which replaces
    the previous one in `coli_build/coli_g0/`: it now holds its initial samples
    plus the new one. The previous version is deleted once the new one is
    checked (`--keep-previous` keeps it in `coli_build/work/update/previous/`).

    `GCA_000005845` falls in the span bucket of `coli_g0`, so only that
    sub-index is merged. `coli_g1` is untouched.

??? warning "Disk space"
    The previous version and the updated one coexist on disk during the merge.
    Plan for at least twice the size of the sub-indices being updated.

---

## Step 5 - Query the updated index ([`query`](../commands/query.md))

```bash
kmhelpers query -r coli_build/ -o results_update/ query.fa
```

??? success "RESULT"
    `coli_g0` now holds 6 samples, the 5 initial ones plus `GCA_000005845`.
    `query.fa` comes from `GCA_000780515`, indexed in `coli_g1`, which still
    scores **1.0**.

    The previous version was deleted once the updated one was registered and
    checked. To compare both versions, build with `--keep-previous`: the
    previous `coli_g0` is then left in `coli_build/work/update/previous/coli_g0/`,
    to delete once done.

---

## Step 6 - Check the result

```bash
# Registered indices and the samples they hold
kmhelpers manage -r coli_build/ list
kmhelpers manage -r coli_build/ info --sh coli_g0
kmhelpers manage -r coli_build/ check
```
