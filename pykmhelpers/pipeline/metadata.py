from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass
class BuscoStats:
    """BUSCO (Benchmarking Universal Single-Copy Orthologs) statistics"""

    busco_complete: float
    busco_single: int
    busco_duplicated: int
    busco_fragmented: int
    busco_missing: int
    busco_dir: str
    format: str


@dataclass
class AssemblyStats:
    """Assembly statistics for a sample"""

    total_nucleotides: int
    ungapped_length: int
    num_contigs: int
    scaffold_n50: int
    scaffold_l50: int
    contig_n50: int
    contig_l50: int
    gc_percent: float
    total_kmers: int
    usable_kmers: int
    k: int
    json: str
    genome_coverage: float
    num_chromosomes: Optional[int] = None
    busco: Optional[BuscoStats] = None


@dataclass
class SampleMetadata:
    """Represents a sample object from the kmindex assembly metadata"""

    sample_id: str
    organism: str
    taxid: int
    genbank_accession: str
    type: str
    assembled: bool
    technology: str
    assembly_stage: str
    data_category: str
    assembly_stats: AssemblyStats
    file_path: str
    extra_info: Optional[Dict[str, Any]] = None
