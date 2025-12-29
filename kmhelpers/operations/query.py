import os
import shutil
import yaml
from typing import List, Optional, Union
from ..core.utils import Toolbox
from ..core.wrapper import KmindexWrapper
from .sequence import Sequence


class KmindexQueryResult:
    def __init__(self, result: dict) -> None:
        self._result = result

    @property
    def result(self):
        return self._result

    def get_index_result(self, index_id) -> dict:
        return self.result.get(index_id, dict)


class KmindexQuery:
    def __init__(self, path: str = "", sequence: Optional[Sequence] = None) -> None:
        """
        Initialize a KmindexQuery object from a file path or Sequence object.

        :param path: Path to a query FASTA file, or where to write the sequence if provided
        :type path: str
        :param sequence: Sequence object to use as query
        :type sequence: Optional[Sequence]
        """
        assert path or sequence, "Either path or sequence string must be provided"
        self._sequence = sequence
        self._path = path
        if sequence:
            if path:
                path = Toolbox.get_canonical_path(path)
                assert not os.path.isfile(path), f"Sequence file already exists: {path}"
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w") as f:
                    f.write(sequence.to_fasta())
        else:
            assert os.path.isfile(path), f"Query file not found: {path}"

    def execute(
        self,
        registry_path: str,
        output_dir="query",
        index_ids: list[str] = [],
        z: int = 6,
        single_query: Optional[str] = None,
        aggregate: bool = False,
        threads: int = 1,
    ):
        """
        Run a query against the kmindex registry.

        :param registry_path: Path to the kmindex registry
        :type registry_path: str
        :param output_dir: Output directory for query results
        :type output_dir: str
        :param index_ids: List of index IDs to query against (empty for all)
        :type index_ids: list[str]
        :param single_query: Query identifier. If provided, all sequences are considered as a unique query.
        :type single_query: Optional[str]
        :param aggregate: Whether to aggregate results from batches into one file.
        :type aggregate: bool
        :param threads: Number of threads to use for the query.
        :type threads: int
        """
        result_dir = os.path.join(output_dir, "result")
        os.makedirs(output_dir, exist_ok=True)

        query_path = os.path.join(output_dir, "query.fa")

        if self._path:
            shutil.copy(self._path, query_path)
        elif self._sequence:
            with open(query_path, "w") as f:
                f.write(self._sequence.to_fasta())

        result = KmindexWrapper().query(
            input_registry=registry_path,
            query_file=query_path,
            output_dir=result_dir,
            names=index_ids,
            single_query=single_query,
            aggregate=aggregate,
            threads=threads,
            zvalue=z,
        )

        # Save result to info.yaml
        info_file = os.path.join(output_dir, "info.yaml")
        with open(info_file, "w") as f:
            yaml.safe_dump(result, f)
