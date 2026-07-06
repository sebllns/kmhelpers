# kmhelpers

<img src="assets/kmhelpers-logo-v1.png" alt="kmhelpers logo" width="80">

A Python toolkit for managing, compressing, and querying [kmindex](https://github.com/tlemane/kmindex) indices efficiently.

---

## What is kmhelpers?

**kmhelpers** is a command-line toolkit built on top of [kmindex](https://github.com/tlemane/kmindex) that automates the full k-mer index lifecycle:

- **Discover** sample files and count k-mers
- **Profile** samples to select optimal Bloom-filter parameters
- **Compose** index definition files from sample lists
- **Build** indices with `apply` or batch them with `pipeline`
- **Query** indices against FASTA/FASTQ sequences
- **Compress** indices for storage efficiency *(under development)*
- **Manage** index registries with full CRUD operations *(under development)*

![Pipeline diagram](diagrams/fig_pipeline_mini_animation.svg)

=== "1 - DESIGN"
    <!-- termynal -->

    ```
    $ kmhelpers design coli_10.txt \
    -o coli_db/ \
    -n coli \
    -S initial \
    -k 25 \
    -b 1.1 \
    -g 2

    GCA_000780515_1_ASM78051v1_genomic_fna:10898876
    GCA_001076125_1_ASM107612v1_genomic_fna:10180102
    GCA_001417575_1_ASM141757v1_genomic_fna:9559455
    GCA_000944435_1_Ec57A_E8C1_MIRA_assembly_genomic_fna:4965700
    GCA_001075925_1_ASM107592v1_genomic_fna:8662789
    GCA_000936715_1_E8C1_assembly_genomic_fna:4960388
    GCA_000939215_1_Ec57A_A7_MIRA_assembly_genomic_fna:5015891
    GCA_001413795_1_ASM141379v1_genomic_fna:9124847
    GCA_001373195_1_57A_A7_assembly_genomic_fna:5014418
    GCA_000938575_1_D1C4_assembly_genomic_fna:4709945
    Listed 10 samples -> coli_db/list/coli_samples_20260706_173255.jsonl
    SUCCESS ('list')
    SUCCESS ('profile')
    Run ID: initial
    Wrote layout: coli_db/compose/coli_layout.yaml
    Composed 10 samples into 2 indices
      coli_g0: 5 samples → 14.7MB
      coli_g1: 5 samples → 34.6MB
    Minimum storage required: 49.2MB
    Exported database to coli_db/compose/coli/initial
    SUCCESS ('compose')
    Done in 25.97s
    ```

=== "2 - BUILD"
    <!-- termynal -->

    ```
    $ kmhelpers build coli_db/compose/coli/initial/coli.yaml -o coli_build/ --show-progress

    Plan coli_db/compose/coli/initial/coli.yaml...
    ► Processing index definition 'coli_g0'...
      └── Sample count: 5
      └── Estimated build size: 14.6MB
    ► Processing index definition 'coli_g1'...
      └── Sample count: 5
      └── Estimated build size: 34.5MB
    SUCCESS ('plan')
    Apply coli_db/compose/coli/initial/coli.yaml...
    Building index 'coli_g0'...
    Building index 'coli_g1'...
    SUCCESS ('apply')
    Done in 20.38s
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
    <!-- termynal -->

    ```
    $ kmhelpers design coli_5_update.txt \
    -o coli_db/ \
    -n coli \
    -S update

    GCA_001413905_1_ASM141390v1_genomic_fna:4648368
    GCA_001413805_1_ASM141380v1_genomic_fna:4675704
    GCA_001413685_1_ASM141368v1_genomic_fna:4668342
    GCA_001413415_1_ASM141341v1_genomic_fna:4668146
    GCA_001309965_1_ASM130996v1_genomic_fna:5157636
    Listed 5 samples -> coli_db/list/coli_samples_20260706_180519.jsonl
    SUCCESS ('list')
    Found existing layout file, skipping 'profile'
    Run ID: update
    Composed 5 samples into 2 indices
      coli_g0: 4 samples → 14.7MB
      coli_g1: 1 samples → 34.6MB
    Minimum storage required: 49.2MB
    Exported database to coli_db/compose/coli/update
    SUCCESS ('compose')
    Done in 12.04s
    ```

    <!-- termynal -->

    ```
    $ kmhelpers build coli_db/compose/coli/update/coli.yaml -o coli_build/ --show-progress

    ```

## Quick links

- [Installation](installation.md)
- [Getting Started](getting-started.md)
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

See [Installation](installation.md) for build instructions.

## License

GPL-3.0-only — Copyright © 2026 Sébastien Bellenous, Genscale, INRIA