# kmhelpers

<img src="assets/kmhelpers-logo-v1.png" alt="kmhelpers logo" width="80">

A Python toolkit for managing, compressing, and querying [kmindex](https://github.com/tlemane/kmindex) indices efficiently.

---

## What is kmhelpers?

**kmhelpers** is a command-line toolkit built on top of [kmindex](https://github.com/tlemane/kmindex) that automates the full k-mer index lifecycle: discovering and profiling samples, composing and building indices, and querying them against FASTA/FASTQ sequences — with compression and registry management *(under development)* on the way.

This typical lifecycle breaks down into four steps, shown below:

1. **DESIGN** — discover samples and generate index definitions.
2. **BUILD** — build k-mer indices from those definitions.
3. **QUERY** — search the indices with FASTA/FASTQ sequences.
4. **UPDATE** — add new samples to an existing index without rebuilding from scratch.


![Pipeline diagram](diagrams/fig_pipeline_mini_animation.svg)

=== "1 - DESIGN"
    <!-- termynal -->

    ```
    $ kmhelpers design coli_10.txt -o coli_db/ -n coli -S initial -k 25 -b 1.1 -g 2

    Listed 10 samples -> coli_db/list/coli_samples_20260706_173255.jsonl
    SUCCESS ('list')
    SUCCESS ('profile')
    Composed 10 samples into 2 indices
      coli_g0: 5 samples → 14.7MB
      coli_g1: 5 samples → 34.6MB
    SUCCESS ('compose')
    Done in 25.97s
    ```

=== "2 - BUILD"
    <!-- termynal -->

    ```
    $ kmhelpers build coli_db/compose/coli/initial/coli.yaml -o coli_build/ --show-progress

    SUCCESS ('plan')
    Building index 'coli_g161_initial_p0'...
    Building index 'coli_g170_initial_p0'...
    Merging ['coli_g161_initial_p0'] into 'coli_g0'
    Merging ['coli_g170_initial_p0'] into 'coli_g1'
    SUCCESS ('apply')
    Done in 18.22s
    ```

=== "3 - QUERY"
    <!-- termynal -->

    ```
    $ kmhelpers query -r coli_build/ -o results/ query.fa

    [1/1] Querying: query...
    Time: 0.10s
    Results: results/query/result
    Completed in 0.10s
    Output directory: results/
    Done in 0.11s
    ```

=== "4 - UPDATE"
    **4.1 - Design**  

    <!-- termynal -->

    ```
    $ kmhelpers design coli_5_update.txt -o coli_db/ -n coli -S update

    Listed 5 samples -> coli_db/list/coli_samples_20260706_180519.jsonl
    SUCCESS ('list')
    Found existing layout file, skipping 'profile'
    Composed 5 samples into 2 indices
      coli_g0: 4 samples → 14.7MB
      coli_g1: 1 samples → 34.6MB
    SUCCESS ('compose')
    Done in 12.04s
    ```

    **4.2 - Build**  
    
    <!-- termynal -->

    ```
    $ kmhelpers build coli_db/compose/coli/update/coli.yaml -o coli_build/ --show-progress

    SUCCESS ('plan')
    Building index 'coli_g161_update_p0'...
    Building index 'coli_g170_update_p0'...
    Found backup version of 'coli_g0': ['coli_g0_20260707_200039']
    Merging ['coli_g161_update_p0', 'coli_g0_20260707_200039'] into 'coli_g0'
    Found backup version of 'coli_g1': ['coli_g1_20260707_200039']
    Merging ['coli_g170_update_p0', 'coli_g1_20260707_200039'] into 'coli_g1'
    SUCCESS ('apply')
    Done in 7.61s
    ```

!!! info "Performance"
    Most `kmhelpers` commands (`design`, `plan`, `query`, `compose`, ...) complete in a few seconds, since they mainly manipulate metadata and small files. The exception is **`build`** (and the underlying `apply` build/merge steps): actual k-mer counting and Bloom-filter construction are CPU- and I/O-bound, so runtime scales with sample count and data size — expect build/merge steps to take anywhere from seconds to hours depending on dataset size, `--threads`, and storage speed.

## Quick links

- [Installation](getting-started/installation.md)
- [Quick Start](getting-started/getting-started.md)
- [Command Reference](commands/index.md)
- [Changelog](changelog.md)
- [Repository](https://github.com/sebllns/kmhelpers)

## Version & Requirements

**kmhelpers v0.6.3**  · Python ≥ 3.8

| Tool | Version |
|---|---|
| [kmindex](https://github.com/tlemane/kmindex) | ≥ 0.6.1 |
| [kmtricks](https://github.com/tlemane/kmtricks) | ≥ 1.6.0 |
| [ntCard](https://github.com/bcgsc/ntCard) | ≥ 1.2.2 |

See [Installation](getting-started/installation.md) for build instructions.

## License

GPL-3.0-only — Copyright © 2026 Sébastien Bellenous, Genscale, INRIA