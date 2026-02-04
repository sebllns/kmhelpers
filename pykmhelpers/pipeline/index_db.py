from dataclasses import dataclass
from typing import Optional, Dict, Any
import re
import json
import yaml


@dataclass
class Sample:
    id: Optional[str]
    files: list[str]
    kmer_count: int


@dataclass
class Index:
    id: str
    kmer_size: int
    minim_size: int
    partition_count: int
    span: int
    bf_size: int
    stored_size_bytes: int
    stored_size_str: str
    sample_count: int
    samples: dict[str, Sample]


IndexTable = dict[str, Index]


class IndexDefinitionTools:
    def __init__(self) -> None:
        pass

    def load_db(self, filename: str) -> IndexTable:
        """Load index database from JSON or YAML file."""
        with open(filename, "r") as f:
            if filename.endswith(".json"):
                data = json.load(f)
            elif filename.endswith((".yaml", ".yml")):
                data = yaml.safe_load(f)
            else:
                raise ValueError(f"Unsupported file format: {filename}")

        indices = {}
        for index_id, index_data in data.items():
            samples = {}
            for sample_id, sample_data in index_data.get("samples", {}).items():
                samples[sample_id] = Sample(
                    id=sample_id,
                    files=sample_data.get("files", []),
                    kmer_count=sample_data.get("kmer_count", 0),
                )

            indices[index_id] = Index(
                id=index_data.get("id"),
                kmer_size=index_data.get("kmer_size"),
                minim_size=index_data.get("minim_size"),
                partition_count=index_data.get("partition_count"),
                span=index_data.get("span"),
                bf_size=index_data.get("bf_size"),
                stored_size_bytes=index_data.get("stored_size_bytes"),
                stored_size_str=index_data.get("stored_size_str"),
                sample_count=index_data.get("sample_count"),
                samples=samples,
            )

        return indices

    def save_db(self, index_table: IndexTable, filename: str) -> None:
        """Save index database to JSON or YAML file."""
        data = {}

        for index_id, index in sorted(index_table.items()):
            samples_data = {}
            for sample_id, sample in index.samples.items():
                samples_data[sample_id] = {
                    "id": sample.id,
                    "kmer_count": sample.kmer_count,
                    "files": sample.files,
                }

            data[index_id] = {
                "id": index.id,
                "kmer_size": index.kmer_size,
                "minim_size": index.minim_size,
                "partition_count": index.partition_count,
                "span": index.span,
                "bf_size": index.bf_size,
                "sample_count": index.sample_count,
                "stored_size_bytes": index.stored_size_bytes,
                "stored_size_str": index.stored_size_str,
                "samples": samples_data,
            }

        with open(filename, "w") as f:
            if filename.endswith(".json"):
                json.dump(data, f, indent=2, sort_keys=False)
            elif filename.endswith((".yaml", ".yml")):
                yaml.dump(data, f, default_flow_style=False, sort_keys=False)
            else:
                raise ValueError(f"Unsupported file format: {filename}")

    def clean_sample_id(self, sample_id) -> str:
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
