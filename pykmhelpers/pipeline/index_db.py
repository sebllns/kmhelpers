from dataclasses import dataclass
from typing import Optional
import re
import json
import yaml
from ..core.bloom_filter import BloomFilterSpecs
from ..core.byte import ByteCounter, SizeFormat


@dataclass
class Sample:
    id: Optional[str]
    files: list[str]
    kmer_count: int


@dataclass
class Index:
    id: str
    kmhelpers_version: str
    kmer_size: int
    partition_count: int
    span: int
    bf_size: int
    samples: dict[str, Sample]

    @property
    def sample_count(self):
        return len(self.samples)

    def add_sample(self, sample_id: str, sample: Sample):
        self.samples[sample_id] = sample

    def get_bf_specs(self):
        return BloomFilterSpecs(self.bf_size, self.sample_count, self.partition_count)

    def get_stored_size(self):
        return ByteCounter.auto(self.get_bf_specs().total_storage_size(), SizeFormat.BYTE)
    
    def get_stored_size_per_partition(self):
        return ByteCounter.auto(self.get_bf_specs().partition_file_size(), SizeFormat.BYTE)


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

            parameters = index_data.get("parameters")

            indices[index_id] = Index(
                id=index_id,
                kmhelpers_version=parameters.get("kmhelpers_version", "0.6.0"),
                kmer_size=parameters.get("kmer_size", 25),
                partition_count=parameters.get("partition_count", 256),
                bf_size=parameters.get("bf_size"),
                span=index_data.get("infos", {}).get("span", 0),
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
                    "kmer_count": sample.kmer_count,
                    "files": sample.files,
                }

            stored_size = index.get_stored_size()
            partition_stored_size = index.get_stored_size_per_partition()

            infos = {
                "span": index.span,
                "sample_count": index.sample_count,
                "total_stored_size_bytes": stored_size.byte_count,
                "total_stored_size_str": str(stored_size),
                "partition_stored_size_bytes": partition_stored_size.byte_count,
                "partition_stored_size_str": str(partition_stored_size),              
            }

            parameters = {
                "kmer_size": index.kmer_size,
                "partition_count": index.partition_count,
                "bf_size": index.bf_size,
            }

            data[index_id] = {
                "parameters": parameters,
                "infos": infos,
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
