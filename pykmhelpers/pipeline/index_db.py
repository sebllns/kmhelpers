import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import yaml

from ..core.bloom_filter import BloomFilterSpecs
from ..core.byte import ByteCounter, SizeFormat


class DbFields(str, Enum):
    PARENT_INDEX = "parent_index"


@dataclass
class Item:
    id: int = field(default=0)
    name: Optional[str] = None
    links: Optional[dict[str, str]] = None

    def __init_subclass__(cls, auto_increment=False, unique_name=False, **kwargs):
        super().__init_subclass__(**kwargs)
        if auto_increment:
            cls._id_counter = 0
            cls._auto_increment_enabled = True
        if unique_name:
            cls._used_names = set()
            cls._unique_name_enabled = True

    def __post_init__(self):
        # Auto-increment ID
        if hasattr(type(self), "_auto_increment_enabled") and self.id == 0:
            type(self)._id_counter += 1
            self.id = type(self)._id_counter

        # Global uniqueness check
        if hasattr(type(self), "_unique_name_enabled") and self.name:
            if self.name in type(self)._used_names:
                raise ValueError(
                    f"Name '{self.name}' already exists in {type(self).__name__}"
                )
            type(self)._used_names.add(self.name)

    def create_link(self, name: str, value: str):
        if not self.links:
            self.links = {}
        self.links[name] = value

    def get_link(self, name: str) -> Optional[str]:
        if self.links:
            return self.links.get(name)
        return None


@dataclass
class Span(Item, auto_increment=False):
    value: int = 0
    index_table: dict[str, IndexDefinition] = field(default_factory=dict)

    def get_sample_count(self):
        return sum(index.sample_count for index in self.index_table.values())

    def get_total_stored_size(self):
        total_bytes = sum(
            index.get_stored_size().byte_count for index in self.index_table.values()
        )
        return ByteCounter.auto(total_bytes, SizeFormat.BYTE)


@dataclass
class Sample(Item, auto_increment=True):
    parent_index: Optional["IndexDefinition"] = field(default=None, repr=False)
    files: list[str] = field(default_factory=list)
    kmer_count: int = 0


@dataclass
class IndexDefinition(Item, auto_increment=True):
    parent_db: Optional["IndexDB"] = field(default=None, repr=False)
    kmhelpers_version: str = "undefined"
    index_type: str = "kmindex"
    kmer_size: int = 0
    partition_count: int = 0
    span: int = 0
    bf_size: int = 0
    samples: dict[str, Sample] = field(default_factory=dict)

    @property
    def sample_count(self):
        return len(self.samples)

    def add_sample(self, sample_id: str, sample: Sample):
        # Check sample name uniqueness within this Index
        if sample.name and any(s.name == sample.name for s in self.samples.values()):
            raise ValueError(
                f"Sample name '{sample.name}' already exists in Index '{self.name}'"
            )
        sample.parent_index = self
        self.samples[sample_id] = sample

    def get_bf_specs(self):
        return BloomFilterSpecs(self.bf_size, self.sample_count, self.partition_count)

    def get_stored_size(self):
        return ByteCounter.auto(
            self.get_bf_specs().total_storage_size(), SizeFormat.BYTE
        )

    def get_stored_size_per_partition(self):
        return ByteCounter.auto(
            self.get_bf_specs().partition_file_size(), SizeFormat.BYTE
        )


@dataclass
class IndexDB(Item, auto_increment=True, unique_name=True):
    index_table: dict[str, IndexDefinition] = field(default_factory=dict)

    def add_index(self, index: IndexDefinition):
        assert index.name, "Index name empty or null"
        assert not index.name in self.index_table, f"Duplicate name: {index.name}"
        index.parent_db = self
        self.index_table[index.name] = index

    def create_index(
        self,
        index_id: str,
        kmer_size: int,
        span: int,
        bf_size: int,
        partition_count: int,
    ) -> IndexDefinition:
        i = IndexDefinition(
            name=index_id,
            kmer_size=kmer_size,
            bf_size=bf_size,
            partition_count=partition_count,
            span=span,
        )
        self.add_index(i)
        return i


class IndexDefinitionTools:
    def __init__(self) -> None:
        pass

    def get_index_name(self, db_name: str, prefix: str, span: int, segment: int) -> str:
        return f"{db_name}_{prefix}_{span}_{segment}"

    def load_db(self, filename: str) -> IndexDB:
        """Load index database from JSON or YAML file."""
        with open(filename, "r") as f:
            if filename.endswith(".json"):
                data = json.load(f)
            elif filename.endswith((".yaml", ".yml")):
                data = yaml.safe_load(f)
            else:
                raise ValueError(f"Unsupported file format: {filename}")

        index_db = IndexDB()
        for index_id, index_data in data.items():
            samples = {}
            for sample_id, sample_data in index_data.get("samples", {}).items():
                samples[sample_id] = Sample(
                    name=sample_id,
                    files=sample_data.get("files", []),
                    kmer_count=sample_data.get("kmer_count", 0),
                )

            parameters = index_data.get("parameters")

            index = IndexDefinition(
                name=index_id,
                kmhelpers_version=parameters.get("kmhelpers_version", "0.6.0"),
                kmer_size=int(parameters.get("kmer_size", "25")),
                partition_count=int(parameters.get("partition_count", "256")),
                bf_size=int(parameters.get("bf_size")),
                span=index_data.get("infos", {}).get("span", 0),
                index_type=index_data.get("type", "kmindex"),
                samples=samples,
            )

            if DbFields.PARENT_INDEX.value in parameters:
                index.create_link(
                    DbFields.PARENT_INDEX.value,
                    parameters.get(DbFields.PARENT_INDEX.value),
                )

            index_db.add_index(index)

        return index_db

    def save_db(self, index_db: IndexDB, filename: str) -> None:
        """Save index database to JSON or YAML file."""
        data = {}

        for index_id, index in sorted(index_db.index_table.items()):
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
                "kmer_size": str(index.kmer_size),
                "partition_count": str(index.partition_count),
                "bf_size": str(index.bf_size),
            }

            parent = index.get_link(DbFields.PARENT_INDEX.value)

            if parent:
                parameters[DbFields.PARENT_INDEX.value] = parent

            data[index_id] = {
                "kmhelpers_version": index.kmhelpers_version,
                "type": index.index_type,
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
