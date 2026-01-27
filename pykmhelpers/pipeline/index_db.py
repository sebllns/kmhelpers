from dataclasses import dataclass
from typing import Optional, Dict, Any
import re 

@dataclass
class Sample:
    id: Optional[str]
    path: list[str]
    kmer_count: int

@dataclass
class Index:
    id: str
    partition_count: int
    bf_size: int
    stored_size_bytes: int
    stored_size_str: str
    sample_count: int
    samples: dict[str,Sample]

@dataclass
class Db: 
    indices: dict[str,Index]  

def clean_sample_id(sample_id):
    """
    Clean sample_id by:
    1. Replace special characters (non-alphanumeric except underscore) with underscore
    2. Remove duplicate consecutive underscores
    3. Remove leading underscores
    """
    # Replace special characters with underscore
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", sample_id)

    # Remove duplicate consecutive underscores
    cleaned = re.sub(r"_+", "_", cleaned)

    # Remove leading underscores
    cleaned = cleaned.lstrip("_")

    return cleaned
