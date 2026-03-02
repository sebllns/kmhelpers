from dataclasses import dataclass
from enum import Enum
from typing import Optional

from ..operations.builder import IndexBuilder
from .index_db import IndexDefinition, IndexDefinitionTools


class ApplyStatus(str, Enum):
    """Status of an apply operation."""

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    DRY_RUN = "dry_run"


class IndexOps:
    def __init__(self, config: dict) -> None:
        self._config = config or {}

    @property
    def minimizer_length(self) -> int:
        return self._config.get("minimizer_length", 10)

    def has_field_in_config(self, field_name: str) -> bool:
        return field_name in self._config

    def _build_single(self, index_definition: IndexDefinition):
        pass

    def plan(self, def_file: str):
        pass

    def apply(self, def_file: str):
        # Load desired state
        idt = IndexDefinitionTools()
        try:
            dbs = idt.deserialize(def_file)
        except Exception as e:
            logger.error(f"Failed to load definition file '{def_file}': {e}")
            return ApplyStatus.FAILED
