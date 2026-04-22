import json
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import yaml

from ..core.bloom_filter import BloomFilterSpecs
from ..core.byte import ByteCounter, SizeFormat


class SerializedDataType(str, Enum):
    INDEX_DEFINITION = "index"
    SPAN_DEFINITION = "span"


class DbFields(str, Enum):
    # Base Item fields
    ID = "id"
    NAME = "name"
    LINKS = "links"

    # Index fields
    PARENT_INDEX = "parent_index"
    ABUNDANCE_MIN = "abundance_min"
    ASSEMBLED = "assembled"
    KMER_SIZE = "kmer_size"
    PARTITION_COUNT = "partition_count"
    SPAN = "span"
    BF_SIZE = "bf_size"
    KMHELPERS_VERSION = "kmhelpers_version"
    INDEX_TYPE = "index_type"
    SAMPLES = "samples"
    INFOS = "infos"
    PARAMETERS = "parameters"
    INFO_SAMPLE_COUNT = "sample_count"

    # Sample fields
    FILES = "files"
    KMER_COUNT = "kmer_count"
    ORIGINAL_ID = "original_id"

    def get_default(self):
        """Get default value for this field, or None if no default is defined."""
        defaults = {
            DbFields.ID: 0,
            DbFields.NAME: None,
            DbFields.LINKS: None,
            DbFields.PARENT_INDEX: None,
            DbFields.ABUNDANCE_MIN: 2,
            DbFields.ASSEMBLED: False,
            DbFields.KMER_SIZE: 25,
            DbFields.PARTITION_COUNT: 0,
            DbFields.SPAN: 0,
            DbFields.BF_SIZE: 0,
            DbFields.KMHELPERS_VERSION: "undefined",
            DbFields.INDEX_TYPE: "undefined",
            DbFields.FILES: [],
            DbFields.KMER_COUNT: 0,
            DbFields.SAMPLES: {},
        }
        return defaults.get(self)


@dataclass
class Item:
    id: int = field(default=DbFields.ID.get_default() or 0)
    name: Optional[str] = DbFields.NAME.get_default()
    links: Optional[dict[str, str]] = DbFields.LINKS.get_default()

    def __init_subclass__(cls, auto_increment=False, unique_name=False, **kwargs):
        super().__init_subclass__(**kwargs)
        if auto_increment:
            cls._id_counter = 0
            cls._auto_increment_enabled = True
        if unique_name:
            cls._instances: dict[str, "Item"] = {}
            cls._unique_name_enabled = True

    def __post_init__(self):
        # Auto-increment ID
        if hasattr(type(self), "_auto_increment_enabled") and self.id == 0:
            type(self)._id_counter += 1
            self.id = type(self)._id_counter

        # Global uniqueness check
        if hasattr(type(self), "_unique_name_enabled") and self.name:
            if self.name in type(self)._instances:
                raise ValueError(
                    f"Name '{self.name}' already exists in {type(self).__name__}"
                )
            type(self)._instances[self.name] = self

    def __del__(self):
        if hasattr(type(self), "_unique_name_enabled") and self.name:
            if type(self)._instances and self.name in type(self)._instances:
                del type(self)._instances[self.name]

    @classmethod
    def get_instance(cls, name: str) -> Optional["Item"]:
        if hasattr(cls, "_unique_name_enabled"):
            return cls._instances.get(name)
        return None

    @classmethod
    def remove_instance(cls, name: str) -> Optional["Item"]:
        if hasattr(cls, "_unique_name_enabled"):
            return cls._instances.pop(name)
        return None

    @classmethod
    def get_all(cls) -> Optional[list["Item"]]:
        if hasattr(cls, "_unique_name_enabled"):
            return list(cls._instances.values())
        return None

    def create_link(self, name: str, value: str):
        if not self.links:
            self.links = {}
        self.links[name] = value

    def has_link(self, name: str) -> bool:
        return self.links is not None and name in self.links

    def get_link(self, name: str) -> Optional[str]:
        if self.links:
            return self.links.get(name)
        return None


@dataclass
class Span(Item, auto_increment=False):
    value: int = DbFields.SPAN.get_default() or 0
    index_table: dict[str, "IndexDefinition"] = field(default_factory=dict)

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
    kmhelpers_version: str = DbFields.KMHELPERS_VERSION.get_default() or ""
    index_type: str = DbFields.INDEX_TYPE.get_default() or ""
    kmer_size: int = DbFields.KMER_SIZE.get_default() or 0
    partition_count: int = DbFields.PARTITION_COUNT.get_default() or 0
    span: int = DbFields.SPAN.get_default() or 0
    bf_size: int = DbFields.BF_SIZE.get_default() or 0
    abundance_min: int = DbFields.ABUNDANCE_MIN.get_default() or 2
    assembled: bool = DbFields.ASSEMBLED.get_default() or False
    samples: dict[str, Sample] = field(default_factory=dict)
    merge_name: Optional[str] = None

    @property
    def sample_count(self):
        return len(self.samples)

    def get_parent(self):
        return self.get_link(DbFields.PARENT_INDEX.value)

    def set_parent(self, parent_name):
        return self.create_link(
            DbFields.PARENT_INDEX.value,
            parent_name,
        )

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
    index_table: dict[str, "IndexDefinition"] = field(default_factory=dict)
    span_table: dict[int, "Span"] = field(default_factory=dict)
    # merge_table: dict[str, dict] = field(default_factory=dict)

    def add_index(self, index: IndexDefinition):
        assert index.name, "Index name empty or null"
        assert index.name not in self.index_table, f"Duplicate name: {index.name}"
        index.parent_db = self
        self.index_table[index.name] = index
        if index.span not in self.span_table:
            self.span_table[index.span] = Span(
                name=str(index.span),
            )
        self.span_table[index.span].index_table[index.name] = index
        # parent_index = index.get_parent()
        # if parent_index:
        #     if not self.merge_table:
        #         self.merge_table = {}
        #     merged_name = parent_index[:-2]
        #     if not merged_name in self.merge_table:
        #         self.merge_table[merged_name] = {}
        #         self.merge_table[merged_name]["parts"] = [parent_index]
        #     self.merge_table[merged_name]["parts"].append(index.name)

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

    def get_index(self, name):
        return self.index_table.get(name)


class IndexDefinitionTools:
    def __init__(self) -> None:
        pass

    def get_abundance_min(self, assembled: bool) -> int:
        return 1 if assembled else 2

    def get_field_name(self, field: DbFields) -> str:
        return field.value

    def has_field(self, field: DbFields, table: dict) -> bool:
        return field.value in table

    def get_field_safe(self, field: DbFields, table: dict):
        return table.get(field.value, field.get_default())

    def get_field(self, field: DbFields, table: dict):
        value = self.get_field_safe(field, table)
        if value is None:
            raise ValueError(f"Field not found or no default: {field.value}")
        else:
            return value

    def get_merge_name(self, db_name: str, prefix: str, span: int) -> str:
        return f"{db_name}_{prefix}_{span}"

    def get_index_name(self, db_name: str, prefix: str, span: int, segment: int) -> str:
        return f"{db_name}_{prefix}_{span}_p{segment}"

    def _load_db_file(self, filename: str) -> IndexDB:
        """Load index database from JSON or YAML file."""
        data = self.deserialize(filename)
        assert data, f"Could not deserialize definition data from {filename}"
        assert "type" in data, "Definition file is missing required field 'type'"
        assert "data" in data, "Definition file is missing required field 'data'"
        assert (
            data["type"] == SerializedDataType.INDEX_DEFINITION
        ), f"Bad input type: {data["type"]}"

        data = data["data"]
        index_db = IndexDB(name=os.path.splitext(os.path.basename(filename))[0])
        for index_id, index_data in data.items():
            samples = {}
            for sample_id, sample_data in index_data.get(
                self.get_field_name(DbFields.SAMPLES), {}
            ).items():
                samples[sample_id] = Sample(
                    name=sample_id,
                    files=self.get_field(DbFields.FILES, sample_data),
                    kmer_count=int(self.get_field(DbFields.KMER_COUNT, sample_data)),
                )

            parameters = index_data.get(self.get_field_name(DbFields.PARAMETERS))

            index = IndexDefinition(
                name=index_id,
                kmhelpers_version=str(
                    self.get_field(DbFields.KMHELPERS_VERSION, index_data)
                ),
                kmer_size=int(self.get_field(DbFields.KMER_SIZE, parameters)),
                partition_count=int(
                    self.get_field(DbFields.PARTITION_COUNT, parameters)
                ),
                bf_size=int(self.get_field(DbFields.BF_SIZE, parameters)),
                span=index_data.get(self.get_field_name(DbFields.INFOS), {}).get(
                    self.get_field_name(DbFields.SPAN), 0
                ),
                index_type=str(self.get_field(DbFields.INDEX_TYPE, index_data)),
                assembled=bool(self.get_field(DbFields.ASSEMBLED, index_data)),
                abundance_min=int(self.get_field(DbFields.ABUNDANCE_MIN, parameters)),
                samples=samples,
            )

            if self.has_field(DbFields.PARENT_INDEX, parameters):
                index.create_link(
                    self.get_field_name(DbFields.PARENT_INDEX),
                    self.get_field(DbFields.PARENT_INDEX, parameters),
                )

            index_db.add_index(index)

        return index_db

    def _load_db_dir(self, path: str) -> list[IndexDB]:
        assert os.path.isdir(path), f"Not a directory: {path}"
        res = []
        for e in os.scandir(path):
            if e.is_file and e.path.endswith((".yaml", ".yml", ".json")):
                try:
                    res.append(self._load_db_file(e.path))
                except Exception as e:
                    print(e)
                    pass
        return res

    def serialize(self, filename, data, sort_keys=False):
        with open(filename, "w") as f:
            if filename.endswith(".json"):
                json.dump(data, f, indent=2, sort_keys=sort_keys)
            elif filename.endswith((".yaml", ".yml")):
                yaml.dump(data, f, default_flow_style=False, sort_keys=sort_keys)
            else:
                raise ValueError(f"Unsupported file format: {filename}")

    def deserialize(self, filename: str) -> Any:
        data = None
        with open(filename, "r") as f:
            if filename.endswith(".json"):
                data = json.load(f)
            elif filename.endswith((".yaml", ".yml")):
                data = yaml.safe_load(f)
            else:
                raise ValueError(f"Unsupported file format: {filename}")
        return data

    def save_db(self, index_db: IndexDB, filename: str) -> None:
        """Save index database to JSON or YAML file."""
        data = {}

        for index_id, index in sorted(index_db.index_table.items()):
            samples_data = {}
            for sample_id, sample in index.samples.items():
                samples_data[sample_id] = {
                    self.get_field_name(DbFields.KMER_COUNT): sample.kmer_count,
                    self.get_field_name(DbFields.FILES): sample.files,
                }
                if sample.has_link(DbFields.ORIGINAL_ID):
                    samples_data[sample_id][
                        self.get_field_name(DbFields.ORIGINAL_ID)
                    ] = sample.get_link(DbFields.ORIGINAL_ID)

            stored_size = index.get_stored_size()
            partition_stored_size = index.get_stored_size_per_partition()

            infos = {
                self.get_field_name(DbFields.SPAN): index.span,
                self.get_field_name(DbFields.INFO_SAMPLE_COUNT): index.sample_count,
                # self.get_field_name(
                #     DbFields.INFO_TOTAL_STORED_SIZE_BYTES
                # ): stored_size.byte_count,
                # self.get_field_name(DbFields.INFO_TOTAL_STORED_SIZE_STR): str(
                #     stored_size
                # ),
                # self.get_field_name(
                #     DbFields.INFO_PARTITION_STORED_SIZE_BYTES
                # ): partition_stored_size.byte_count,
                # self.get_field_name(DbFields.INFO_PARTITION_STORED_SIZE_STR): str(
                #     partition_stored_size
                # ),
            }

            parameters = {
                self.get_field_name(DbFields.KMER_SIZE): str(index.kmer_size),
                self.get_field_name(DbFields.PARTITION_COUNT): str(
                    index.partition_count
                ),
                self.get_field_name(DbFields.BF_SIZE): str(index.bf_size),
                self.get_field_name(DbFields.ABUNDANCE_MIN): str(index.abundance_min),
            }

            parent = index.get_link(DbFields.PARENT_INDEX.value)

            if parent:
                parameters[DbFields.PARENT_INDEX.value] = parent

            data[index_id] = {
                self.get_field_name(
                    DbFields.KMHELPERS_VERSION
                ): index.kmhelpers_version,
                self.get_field_name(DbFields.INDEX_TYPE): index.index_type,
                self.get_field_name(DbFields.ASSEMBLED): index.assembled,
                self.get_field_name(DbFields.PARAMETERS): parameters,
                self.get_field_name(DbFields.INFOS): infos,
                self.get_field_name(DbFields.SAMPLES): samples_data,
            }

        self.serialize(
            filename, {"type": SerializedDataType.INDEX_DEFINITION.value, "data": data}
        )

    def load_db(self, path: str) -> list[IndexDB]:
        if os.path.isfile(path) and path.endswith((".yaml", ".yml", ".json")):
            return [self._load_db_file(path)]
        elif os.path.isdir(path):
            return self._load_db_dir(path)
        raise NotImplementedError(f"Can not load DB from {path}: unsupported format.")

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
