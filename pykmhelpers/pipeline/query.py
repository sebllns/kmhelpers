import json
import os
import shutil
import sys
from pathlib import Path
from typing import Optional

import yaml

from pykmhelpers.core.kmindex_wrapper import KmindexWrapper
from pykmhelpers.core.sequence import Sequence
from pykmhelpers.core.utils import Toolbox


class KmindexQueryResult:
    def __init__(self, file: str) -> None:
        self._result = {}
        if file:
            self.load_json(file)

    @property
    def result(self):
        return self._result

    def get_index_result(self, index_id) -> dict:
        return self.result.get(index_id, dict)

    def __eq__(self, other) -> bool:
        """Compare two KmindexQueryResult objects based on their results."""
        if not isinstance(other, KmindexQueryResult):
            return False
        return self._result == other._result

    def load_json(self, file):
        """Load and parse the JSON file."""
        with open(file, "r") as f:
            self._result = json.load(f)

        if not self._result:
            raise ValueError("Empty JSON file")

        self.index_name = list(self._result.keys())[0]
        self.queries = self._result[self.index_name]

    def max_score(self, sample):
        max_score = 0
        for _, samples in self.queries.items():
            max_score = max(max_score, samples.get(sample, 0))
        return max_score

    def generate_markdown(self, threshold: float = 0.0) -> str:
        """Generate simple Markdown tables."""
        lines = []

        for query_name, samples in self.queries.items():
            # Table header with legend
            lines.append(
                f"## Query {query_name} on {self.index_name} - Filter scores ≥ {threshold}\n"
            )

            # Sort by score (descending) and filter by threshold
            sorted_samples = sorted(
                [(s, sc) for s, sc in samples.items() if sc >= threshold],
                key=lambda x: x[1],
                reverse=True,
            )

            col_w = max((len(s) for s, _ in sorted_samples), default=len("Sample"))
            col_w = max(col_w, len("Sample"))
            lines.append(f"| {'Sample':<{col_w}} | Score |")
            lines.append(f"| {'-' * col_w} | ----- |")

            for sample, score in sorted_samples:
                lines.append(f"| {sample:<{col_w}} | {score:.3f} |")

            lines.append("")  # Empty line between queries

        return "\n".join(lines)

    def generate_html(self, threshold: float = 0.0) -> str:
        """Generate simple HTML tables."""
        html = []

        # HTML header
        html.append("<!DOCTYPE html>")
        html.append("<html lang='en'>")
        html.append("<head>")
        html.append("    <meta charset='UTF-8'>")
        html.append(
            "    <meta name='viewport' content='width=device-width, initial-scale=1.0'>"
        )
        html.append(f"    <title>kmindex Results - {self.index_name}</title>")
        html.append("    <style>")
        html.append(
            "        body { font-family: Arial, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; }"
        )
        html.append(
            "        h2 { color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 8px; margin-top: 30px; }"
        )
        html.append(
            "        table { border-collapse: collapse; width: 100%; margin: 20px 0; }"
        )
        html.append(
            "        th, td { padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }"
        )
        html.append(
            "        th { background-color: #3498db; color: white; font-weight: bold; position: sticky; top: 0; }"
        )
        html.append("        tr:hover { background-color: #f5f5f5; }")
        html.append("        tr:nth-child(even) { background-color: #f9f9f9; }")
        html.append("    </style>")
        html.append("</head>")
        html.append("<body>")

        for query_name, samples in self.queries.items():
            # Table with legend
            html.append(
                f"    <details open><summary><h2>Query {query_name} on {self.index_name} - Filter scores ≥ {threshold}</h2></summary>"
            )
            html.append("    <table>")
            html.append("        <tr><th>Sample</th><th>Score</th></tr>")

            # Sort by score (descending) and filter by threshold
            sorted_samples = sorted(
                [(s, sc) for s, sc in samples.items() if sc >= threshold],
                key=lambda x: x[1],
                reverse=True,
            )

            for sample, score in sorted_samples:
                html.append(f"        <tr><td>{sample}</td><td>{score:.3f}</td></tr>")

            html.append("    </table></details>")

        # HTML footer
        html.append("</body>")
        html.append("</html>")

        return "\n".join(html)

    def generate_csv(self, threshold: float = 0.0) -> str:
        """Generate CSV output."""
        lines = ["query,sample,score"]

        for query_name, samples in self.queries.items():
            sorted_samples = sorted(
                [(s, sc) for s, sc in samples.items() if sc >= threshold],
                key=lambda x: x[1],
                reverse=True,
            )

            for sample, score in sorted_samples:
                lines.append(f"{query_name},{sample},{score:.3f}")

        return "\n".join(lines)

    def generate_json(self, threshold: float = 0.0) -> str:
        """Generate filtered JSON output."""
        filtered = {
            self.index_name: {
                query_name: {s: sc for s, sc in samples.items() if sc >= threshold}
                for query_name, samples in self.queries.items()
            }
        }
        return json.dumps(filtered, indent=2)

    def generate_yaml(self, threshold: float = 0.0) -> str:
        """Generate filtered YAML output."""
        filtered = {
            self.index_name: {
                query_name: {
                    s: round(sc, 3) for s, sc in samples.items() if sc >= threshold
                }
                for query_name, samples in self.queries.items()
            }
        }
        return yaml.dump(filtered, default_flow_style=False, sort_keys=False)

    def convert(self, format: str, threshold: float = 0.01):
        """Convert JSON to specified output format."""

        if format.lower() == "md":
            content = self.generate_markdown(threshold)
        elif format.lower() == "html":
            content = self.generate_html(threshold)
        elif format.lower() == "csv":
            content = self.generate_csv(threshold)
        elif format.lower() == "json":
            content = self.generate_json(threshold)
        elif format.lower() == "yaml":
            content = self.generate_yaml(threshold)
        else:
            raise ValueError(
                f"Unsupported output format: {format}. Use 'md', 'html', 'csv', 'json', or 'yaml'"
            )

        return content


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
        is_compressed: bool = False,
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

        output = KmindexWrapper().query(
            input_registry=registry_path,
            query_file=query_path,
            output_dir=result_dir,
            names=index_ids,
            single_query=single_query,
            aggregate=aggregate,
            threads=threads,
            zvalue=z,
            is_compressed=is_compressed,
        )

        # Save result to info.yaml
        info_file = os.path.join(output_dir, "info.yaml")
        with open(info_file, "w") as f:
            yaml.safe_dump(output, f)

        result = []

        for f in os.listdir(result_dir):
            fpath = os.path.join(result_dir, f)
            if os.path.isfile(fpath) and f.endswith(".json"):
                try:
                    result.append(KmindexQueryResult(fpath))
                except Exception as e:
                    print(f"Could not read result from {fpath}: {e}")

        return result
