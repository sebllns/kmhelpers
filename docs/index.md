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
| [kmindex](https://github.com/tlemane/kmindex) | > 0.6.0 or built from [`next-dev`](https://github.com/tlemane/kmindex/tree/next-dev) branch |
| [kmtricks](https://github.com/tlemane/kmtricks) | ≥ 1.6.0 |
| [ntCard](https://github.com/bcgsc/ntCard) | ≥ 1.2.2 |

See [Installation](installation.md) for build instructions.

## License

GPL-3.0-only — Copyright © 2026 Sébastien Bellenous, Genscale, INRIA