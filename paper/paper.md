---
title: 'kmhelpers: A Python toolkit for automated management of genomic indexes'
tags:
  - Python
  - bioinformatics
  - k-mer indexing
  - kmindex
  - genomics
  - sequence querying
  - Bloom filters
authors:
  - name: Sébastien Bellenous
    orcid: 0009-0002-8429-284X
    affiliation: 1
  - name: Kamil S. Jaron
    orcid: 0000-0003-1470-5450
    affiliation: 2
  - name: Pierre Peterlongo
    orcid: 0000-0003-0776-6407
    affiliation: 1
affiliations:
  - name: Genscale, Univ. Rennes, Inria, CNRS, IRISA - UMR 6074, Rennes, F-35000 France
    index: 1
  - name: Tree of Life, Wellcome Sanger Institute, Hinxton CB10 1SA, UK
    index: 2
date: 2026-07-06
bibliography: paper.bib
---


# Summary

Large-scale genomic sequence search has become a central problem in modern bioinformatics [@marchet2024; @karasikov2025]. A widely used family of methods relies on Bloom filters (BFs) [@bloom] to record, for each indexed sample, which $k$-mers (words of length $k$) it contains; a query then reports the set of samples containing each queried $k$-mer. Building such an index over many samples is not a single operation but a chain of interdependent steps, and each step
demands specialist knowledge: sizing each Bloom filter to its sample, configuring the third-party components used internally by `kmindex` (such as the `findere` [@robidou2021findere]
approximate-membership layer), distributing data and computation, bounding peak RAM, and grouping samples into sub-indexes so that the final index stays small without slowing queries. An error at any step can invalidate downstream results, waste significant computation, or produce an oversized index.

We present `kmhelpers`, an open-source Python toolkit that automates this entire workflow for indexes built with `kmindex` [@lemane2024]. It hides the technical decisions listed above behind a command-line interface (CLI) and a matching Python API that cover every stage of the $k$-mer index lifecycle, from raw samples up to queries, including the federation of independently built indexes into
a single queryable resource.

# Statement of Need

$k$-mer-based sequence databases built with tools such as `kmindex` [@lemane2024] and `kmtricks` [@lemane2022] answer queries accross large sample collections in genomics, metagenomics, and population studies. They were recently used to index 50 petabases of raw sequencing data [@ls]. Yet a wide gap separates having the indexing software installed from running a reproducible, end-to-end, size-optimized indexing workflow.

Crossing that gap currently requires a user to simultaneously master: Bloom filter sizing as a function of each sample's $k$-mer cardinality (number of $k$-mers to be indexed per sample); configuring internal components of `kmindex`; distributing data and computations; controlling the peak memory; and partitioning the samples into sub-indexes that balance index size against query speed. This expertise is not required to obtain *a* functional index but is needed to obtain an *efficient* one that minimizes index size and maximizes query speed under a fixed false-positive-rate constraint.

`kmhelpers` removes that barrier. It makes the complete process of building, updating, and querying a `kmindex` search engine accessible to any group (research teams, sequencing platforms, hospitals, or data-production centers) that holds a potentially large genomic dataset, whether the resulting index is kept private or shared, without repeated manual re-optimization as the dataset grows. This opens to non-specialists both the creation and maintenance of optimized indexes.

Indexes are rarely static: as new samples accumulate, they must be regularly updated. `kmhelpers` therefore also offers an update feature for easily adding new samples to an existing index.

Formally, the input is a set $\mathcal{S}=\{S_1, \dots, S_n\}$ of $n$ genomic samples of various sizes; each $S_i$ is either a raw sequencing dataset or a set of assembled sequences. The output is a `kmindex` index subject to two user-defined limits: (1) the maximum allowed false-positive rate, and (2) the maximum number of sub-indexes, each a file storing a set of BFs as a matrix. `kmhelpers` orchestrates every step between input and output, automating the parametrization
and the data distribution.

# State of the Field

Several tools tackle large-scale sequence search with $k$-mer-based data structures. `BIGSI` [@bradley2019] and `COBS` [@bingmann2019] use compressed Bloom-filter matrices to answer presence/absence queries across collections of sequencing experiments. `HowDeSBT` [@harris2019] and `Mantis` [@pandey2018] rely on sequence Bloom trees and counting quotient filters, respectively. More recent colored-$k$-mer indexes such as `MetaGraph` [@karasikov2025] and `Fulgor` [@fulgor] push scalability further; see [@marchet2024] for a survey. `kmindex`, which
`kmhelpers` wraps, builds on the `kmtricks` [@lemane2022] counting pipeline and
is designed for efficient querying of large sequence collections.

`kmhelpers` does not compete with any of these approaches at the algorithmic level. Its contribution lies in correctly parametrizing `kmindex`'s individual components and orchestrating them into a single, size-optimized workflow. `kmhelpers` implements the decisions a `kmindex` expert would otherwise make by hand: `profile` computes Bloom filter sizes and sample-to-sub-index assignments that minimize total index size under a false-positive-rate constraint; `plan` estimates disk and memory requirements before any build starts; and `manage` federates independently built sub-indexes into one logical index. No dedicated automation layer of this kind existed for `kmindex` prior to `kmhelpers`.

# Software design

## Background: the sub-index structure

A Bloom-filter index stores all BFs of the same size as a single (row-major) matrix in one file. In such a matrix each column is one BF (one sample) and each row records the presence (1) or absence (0) of a $k$-mer across all samples sharing that filter size, assuming a common hash function. A complete index is therefore a set of such matrices, each one a *sub-index* holding all BFs of a given size.

The difficulty is that each BF size must match the number of items it stores, here the distinct $k$-mers of a sample. If all samples had the same number of distinct $k$-mers, every BF would share one size and a single matrix would suffice. This is the ideal case, where only one file is opened per query and one matrix row gives the answer across all $n$ samples. In practice, sample sizes differ by
several orders of magnitude. Sizing every BF for the largest sample wastes enormous storage space. Giving each sample its own single-column matrix minimizes storage but forces a query to open $n$ files (potentially millions), severely slowing down queries. `kmhelpers` takes the middle ground: the user fixes the maximum number of sub-indexes, and the `profile` step chooses the per-sub-index BF size that minimizes total index size under that constraint, before distributing each input sample to its respective sub-index.

## The pipeline

`kmhelpers` exposes the index lifecycle as a sequence of commands, as illustrated in Figure 1:

- **`list`** — recursively discovers all samples in a given directory and counts each sample's distinct $k$-mers using `ntCard` [@mohamadi2017] (unless the counts are provided by the user).
- **`profile`** — determines the best set of sub-index BF sizes given the user-defined maximum number of sub-indexes and target false-positive rate.
- **`compose`** — assigns each sample to its sub-index and generates the *files-of-files* describing the data origin of each sub-index.
- **`plan`** — validates sample files, available disk space, and memory upfront, and emits ready-to-execute pipeline scripts.
- **`apply`** — builds all sub-indexes by invoking `kmindex`, with span-level and name-level filtering.

For ease of use, steps `list`, `profile`, and `compose` can be grouped under a single command named **`design`**, and steps `plan` and `apply` can be grouped under the **`build`** command.

Once an index is built, `kmhelpers` also answers queries (**`query`**). Multi-step workflows can be described as declarative YAML pipelines (**`pipeline`**) and executed in a single command.

An additional command, **`manage`**, lets users register several distinct indexes (built locally or hosted anywhere accessible) into one logical index, redirecting each query to all registered indexes at query time.

![Overview of the `kmhelpers` workflow](figures/workflow_V2.pdf)

## Implementation

`kmhelpers` is implemented in Python ($\geq 3.8$) and distributed via Conda, which installs its bioinformatics dependencies (`kmindex`, `ntCard`) automatically. The CLI is built with `Click` [@click], and the package exposes a public Python API
covering all CLI functionality. Together, the declarative YAML index-definition format and the `plan`/`apply` separation make $k$-mer indexing workflows accessible to researchers who are not experts in the underlying data structures, while remaining flexible enough for large-scale production use.

# Research impact statement

## Applying `kmhelpers` to the "Tree of Life" dataset

In phase two, the Earth Biogenome Project aims to sequence reference genomes of 150,000 family representatives across the tree of life over the next four years [@blaxter2025]. Tree of Life Programme at the Wellcome Sanger Institute is one of the major contributors to this effort with large sequencing projects, such as Darwin Tree of Life for all species found in Britain and Ireland [@darwinTol]. To date, Tree of Life has already released more than 4,000 genomes and is in the process of sequencing an additional 3,000. The project is based on robustly identified specimens, but occasionally long-read datasets and chromatin capture (HiC) sequencing do not match, which might happen due to cryptic species, sequencing hybrid specimens, or mistakes in sample handling either by the collector or during the sequencing process. These cases we refer to as sample swaps.

This project is a perfect use case for applying `kmhelpers`: from input data, here a mixture of raw sequencing reads and assembled genomes, to a final index powering a CLI search engine that is now being used for identification of sample swaps (matching sequencing libraries) at scale. Concretely, `kmhelpers` was applied to 7,394 samples and this project also helped shape the design of `kmhelpers` itself.
The index is continuously updated as new sequencing data are progressively added, which is essential for sustaining detection of sample swaps.

## Using `kmhelpers` for updating the Logan-Search search engine

The Logan-Search search engine [@ls] indexes approximately 50 petabases of sequence data from SRA [@sra]. Since its creation, the SRA database size has doubled. The index of Logan-Search will be updated using `kmhelpers`, also optimizing the sub-indexes design.

# Availability and documentation

`kmhelpers` is released under the GNU General Public License v3.0 and is available at <https://github.com/sebllns/kmhelpers>. The full documentation is available at <https://sebllns.github.io/kmhelpers/>.

# Acknowledgements

The authors thank Téo Lemane for developing `kmindex` and for his support in addressing feature requests and issues raised during the development of `kmhelpers`. We acknowledge the GenOuest core facility (<https://www.genouest.org>) for providing the computing infrastructure. The work was funded by the Inria Challenge "OmicFinder" (<https://project.inria.fr/omicfinder/>), and by the state funding managed by the French National Research Agency under the France 2030 program [ANR-22-PEAE-0005]. KSJ was funded by Wellcome Trust 220540/Z/20/A.

# AI Usage Disclosure

AI assistance was used for constrained tasks (code suggestions and drafting the paper) under strict human review at every stage. AI provider used: Claude (Anthropic, 2025).

<!-- Will automatically add references here in PDF, built from paper.bib -->
# References
