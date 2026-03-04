import logging
import os
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from ..operations.builder import IndexBuilder
from .index_db import IndexDefinition, IndexDefinitionTools

logger = logging.getLogger(__name__)


class ApplyStatus(str, Enum):
    """Status of an apply operation."""

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    DRY_RUN = "dry_run"
    NONE = "none"


class ApplyInputType(str, Enum):
    UNKNOWN = "unknown"
    DIRECTORY = "directory"
    SPAN_REGISTRY = "span registry"
    INDEX_DEFINITION = "index definition"
    NONE = "none"


@dataclass
class ApplyResult:
    status: ApplyStatus = ApplyStatus.NONE
    input_type: ApplyInputType = ApplyInputType.NONE


class IndexOps:
    # PRIVATE METHODS
    def __init__(self, config: dict) -> None:
        self._config = config or {}

    def _build_single(self, index_definition: IndexDefinition):
        pass

    # ---

    # PROPERTIES AND GETTERS
    @property
    def minimizer_length(self) -> int:
        return self._config.get("minimizer_length", 10)

    def has_field_in_config(self, field_name: str) -> bool:
        return field_name in self._config

    # ---

    # PUBLIC METHODS
    def compose(self):
        pass

    def plan(self, def_file: str):
        pass

    def apply(self, path: str) -> ApplyResult:
        # Load desired state
        result = ApplyResult()
        idt = IndexDefinitionTools()

        result.input_type = ApplyInputType.UNKNOWN

        if os.path.isfile(path) and path.endswith((".yaml", ".yml", ".json")):
            data = idt.deserialize(path)
            # TODO
        elif os.path.isdir(path):
            result.input_type = ApplyInputType.DIRECTORY
        if result.input_type in (
            ApplyInputType.DIRECTORY,
            ApplyInputType.INDEX_DEFINITION,
        ):
            try:
                dbs = idt.load_db(path)
            except Exception as e:
                logger.error(f"Failed to load definition file '{path}': {e}")
                result.status = ApplyStatus.FAILED
                return result

        result.status = ApplyStatus.SUCCESS
        return result

    # ---
