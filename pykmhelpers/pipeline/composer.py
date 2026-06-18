"""Core composition logic for building index definition files from sample lists."""

import datetime
import json
import logging
import os
import shutil
from typing import Generator, Optional

import yaml

import pykmhelpers.pipeline.index_db as db
from pykmhelpers.core.bloom_filter import BloomFilterSpecs, SpanManager
from pykmhelpers.core.byte import ByteCounter
from pykmhelpers.core.constants import KMHELPERS_COMMIT, KMHELPERS_VERSION
from pykmhelpers.core.log import Log

logger = logging.getLogger(__name__)


class IndexComposer:

    def __init__(
        self,
        profiles_file=None,
        layout_file=None,
        selected_profile=None,
        name="index",
        abundance_min=1,
        partition_count=0,
        bf_max_size=None,
        partition_min_size=None,
        no_merge=False,
        exact_partition_count=False,
        partition_count_limit=256,
        kmer_size: Optional[int] = None,
        false_positive_rate: Optional[float] = None,
        format="yaml",
        db_tools: Optional[db.IndexDefinitionTools] = None,
    ):
        self.profiles_file = profiles_file
        self.layout_file = layout_file
        self.selected_profile = selected_profile
        self.name = name
        self.abundance_min = abundance_min
        self.partition_count = partition_count
        self.bf_max_size = bf_max_size
        self.partition_min_size = partition_min_size
        self.no_merge = no_merge
        self.exact_partition_count = exact_partition_count
        self.partition_count_limit = partition_count_limit
        self.kmer_size = kmer_size
        self.false_positive_rate = false_positive_rate
        self.format = format
        self.db_tools = db_tools or db.IndexDefinitionTools()

    def run(
        self,
        input_file: str,
        output_dir: str,
        run_id: Optional[str] = None,
        db_instance: Optional[db.IndexDB] = None,
        span_manager: Optional[SpanManager] = None,
    ) -> None:
        """Compose index definition file(s) from a sample list."""
        file_k = read_jsonl_header(input_file)
        file_fp = None

        span_base = 2.0
        allowed_spans: list[int] = []
        spans_properties = {}

        run_id = run_id or datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

        logger.info(f"Run ID: {run_id}")

        run_dir = os.path.realpath(os.path.join(output_dir, run_id))
        os.makedirs(run_dir, exist_ok=True)

        try:
            shutil.copy(input_file, os.path.join(run_dir, f"{self.name}_samples.jsonl"))
        except shutil.SameFileError:
            pass

        if self.layout_file:
            span_base, map = load_layout(self.layout_file)
            allowed_spans = sorted(int(s) for s in map.keys())
            spans_properties = {
                s: {"id": i, "name": map[s]} for i, s in enumerate(allowed_spans)
            }
            logger.debug(
                f"Loaded layout: {self.layout_file} (base={span_base}, spans={allowed_spans})"
            )

        if self.profiles_file:
            file_fp, span_base, profile = load_profile(
                self.profiles_file, self.selected_profile
            )
            if not profile.get("span_list"):
                raise ValueError(f"Profile has no 'span_list' in {self.profiles_file}")
            allowed_spans = sorted(int(s) for s in profile["span_list"])
            spans_properties = self._fill_span_props(allowed_spans)
            out_layout = os.path.realpath(
                os.path.join(output_dir, f"{self.name}_layout.yaml")
            )
            layout_data = {
                "type": "layout",
                "data": {
                    "base": span_base,
                    "map": {s: spans_properties[s]["name"] for s in allowed_spans},
                },
            }
            with open(out_layout, "w") as f:
                yaml.dump(layout_data, f, default_flow_style=False, sort_keys=True)
            logger.info(f"Wrote layout: {out_layout}")

        kmer_size = self.kmer_size or file_k or 25
        false_positive_rate = self.false_positive_rate or file_fp or 0.25

        partition_count = self.partition_count
        auto_partitioning = partition_count == 0
        if auto_partitioning:
            partition_count = 256

        split_count: dict[int, int] = {}
        original_distribution: dict[int, int] = {}
        bf_sizes: dict[int, int] = {}
        span_size: dict[int, int] = {}
        db_instance = db_instance or db.IndexDB(name=self.name)
        span_manager = span_manager or SpanManager(p=false_positive_rate, b=span_base)

        sample_count = 0
        kmer_count_limit = (
            span_manager.max_kmer_count(allowed_spans[-1]) if allowed_spans else 0
        )

        for sample in stream_samples(input_file):
            try:
                if not sample.files or not sample.files[0]:
                    raise ValueError("Invalid path: empty or null")
                prepare_sample(sample=sample, db_tools=self.db_tools)

                if kmer_count_limit and sample.kmer_count > kmer_count_limit:
                    raise ValueError(
                        f"Sample '{sample.name}' has {sample.kmer_count} k-mers, "
                        f"exceeding the limit of {kmer_count_limit} for this layout."
                    )

                span = span_manager.dispatch(sample.kmer_count)
                original_distribution[span] = original_distribution.get(span, 0) + 1
                bf_sizes[span] = span_manager.get_bf_size(span)

                if allowed_spans:
                    promoted = next((s for s in allowed_spans if s >= span), None)
                    if promoted is None:
                        raise ValueError(
                            f"No allowed span >= {span} for sample '{sample.name}' "
                            f"(kmer_count={sample.kmer_count}). Extend the span list."
                        )
                    span = promoted
                    bf_sizes[promoted] = span_manager.get_bf_size(promoted)

                split_count.setdefault(span, 0)
                span_size.setdefault(span, 0)

                index_name = self.db_tools.get_index_name(
                    self.name, run_id, span, split_count[span]
                )
                if index_name not in db_instance.index_table:
                    logger.debug(
                        f"Creating new index: {index_name}, span={span}, bf_size={bf_sizes[span]}"
                    )
                    i = db.IndexDefinition(
                        name=index_name,
                        kmhelpers_version=KMHELPERS_VERSION,
                        kmhelpers_commit=KMHELPERS_COMMIT,
                        kmer_size=kmer_size,
                        index_type="kmindex",
                        span=span,
                        bf_size=bf_sizes[span],
                        partition_count=partition_count,
                        abundance_min=self.abundance_min,
                        sample_file=f"{self.name}_samples.jsonl",
                        samples={},
                    )
                    i.merge_name = spans_properties[span]["name"]
                    db_instance.add_index(i)
                else:
                    logger.debug(f"Adding to existing index: {index_name}")

                if not sample.name:
                    raise ValueError("Invalid ID: empty or null")
                db_instance.index_table[index_name].add_sample(
                    sample_id=sample.name, sample=sample
                )

                span_size[span] += 1
                if (
                    self.bf_max_size
                    and span_size[span] % 8 == 0
                    and self.bf_max_size
                    <= db_instance.index_table[index_name].get_stored_size()
                ):
                    split_count[span] += 1

                sample_count += 1

            except Exception as e:
                Log.handle_exception(
                    logger=logger,
                    e=e,
                    msg=f"Could not process sample '{sample.name}'(L{1+sample.id})",
                    level=logging.WARNING,
                )

        if sample_count == 0:
            raise ValueError(f"No valid sample found in {input_file}")

        logger.info(
            f"Composed {sample_count} samples into {len(db_instance.span_table)} indices"
        )
        for s, index in sorted(db_instance.span_table.items()):
            logger.info(
                f"  {spans_properties[s]["name"]}: {index.get_sample_count()} samples → {str(index.get_total_stored_size())}"
            )

        original_distribution_file = os.path.join(run_dir, f"{self.name}_orig_dist.csv")
        with open(original_distribution_file, "w") as f:
            f.write("span,bf_size,sample_count\n")
            for span_id, count in sorted(original_distribution.items()):
                f.write(f"{span_id},{bf_sizes[span_id]},{count}\n")

        index_summary_file = os.path.join(run_dir, f"{self.name}_summary.csv")
        with open(index_summary_file, "w") as f:
            f.write("name,span,sample_count,stored_size_GB\n")
            for span_id, span_obj in sorted(db_instance.span_table.items()):
                size = span_obj.get_total_stored_size()
                f.write(
                    f"{spans_properties[span_id]["name"]},{span_id},{span_obj.get_sample_count()},{size.byte_count/(1000**3)}\n"
                )

        logger.debug(f"Exporting database in {self.format} format to {run_dir}...")

        partition_min_size = self.partition_min_size
        for i in db_instance.index_table.values():
            if partition_min_size or auto_partitioning:
                partition_min_size = partition_min_size or ByteCounter.from_str("200MB")
                index_name = self.db_tools.get_index_name(self.name, run_id, i.span, 0)
                ref = db_instance.index_table[index_name]
                bf_specs = BloomFilterSpecs(
                    ref.bf_size,
                    ref.sample_count if self.no_merge else span_size[i.span],
                    1,
                )
                partition_max_count = bf_specs.get_auto_partition_count(
                    partition_min_size.byte_count
                )
                if not auto_partitioning:
                    partition_max_count = min(partition_max_count, partition_count)
                i.partition_count = partition_max_count
            if not self.exact_partition_count and i.partition_count > 1:
                i.partition_count = 1 << (i.partition_count - 1).bit_length()
            i.partition_count = min(
                max(4, i.partition_count), self.partition_count_limit
            )
            logger.debug(f"  {i.name}: partitioning into {i.partition_count} files")

        export_db(
            indices_data=db_instance,
            db_tools=self.db_tools,
            output_dir=run_dir,
            format=self.format,
            split=True,
            db_name=self.name,
        )

        logger.info(f"Exported database to {run_dir}")

    def _fill_span_props(self, allowed_spans):
        return {
            s: {"id": i, "name": self.db_tools.get_merge_name(self.name, i)}
            for i, s in enumerate(allowed_spans)
        }


def load_layout(path: str) -> tuple[float, dict]:
    """Load span_base and allowed span list from a layout YAML file."""
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
        if data.get("type") != "layout":
            raise ValueError(f"Not a layout file: {path}")
        payload = data.get("data", {})
        base = float(payload["base"])
        if "map" not in payload:
            raise ValueError(f"Missing 'map' in layout file: {path}")
        return base, payload["map"]
    except Exception as e:
        logger.error(f"Could not parse layout file {path}: {e}")
        raise


def load_profile(
    profiles_file: str, selected_profile: Optional[str] = None
) -> tuple[Optional[float], float, dict]:
    """Load span list and false-positive rate from a profiles YAML file."""
    with open(profiles_file) as f:
        data = yaml.safe_load(f)

    base = data.get("span_base")
    if not base:
        raise ValueError("No 'span_base' field in profiles file")

    profile_name = selected_profile or data.get("default_profile")
    if not profile_name:
        raise ValueError(
            "No profile selected and no 'default_profile' in profiles file"
        )

    profile = data.get("profiles", {}).get(profile_name)
    if profile is None:
        raise ValueError(f"Profile '{profile_name}' not found in {profiles_file}")

    false_positive_rate = data.get("false_positive_rate")
    return false_positive_rate, base, profile


def export_db(
    indices_data: db.IndexDB,
    db_tools: db.IndexDefinitionTools,
    output_dir: str,
    format: str,
    split: bool,
    db_name: str,
):
    """Export database to YAML or JSON format."""
    os.makedirs(output_dir, exist_ok=True)

    format = format.lower()
    if format not in ("yaml", "json"):
        raise ValueError(f"Unsupported format: {format}. Must be 'yaml' or 'json'")

    total_size = 0
    span_registry = {}

    for span_id, span_data in indices_data.span_table.items():
        span_size = span_data.get_total_stored_size()
        span_registry[span_id] = {
            "infos": {"total_sample_count": span_data.get_sample_count()},
            "indices": {},
        }

        for index_id, index_data in span_data.index_table.items():
            if index_data.merge_name:
                if index_data.merge_name not in span_registry[span_id]["indices"]:
                    span_registry[span_id]["indices"][index_data.merge_name] = []
                span_registry[span_id]["indices"][index_data.merge_name].append(
                    index_data.name
                )
            else:
                span_registry[span_id]["indices"][index_id] = None

            if split:
                db_tools.save_db(
                    db.IndexDB(name=index_id, index_table={index_id: index_data}),
                    os.path.join(output_dir, f"{index_id}.{format}"),
                )

        total_size += span_size.byte_count

    span_registry_file = os.path.join(output_dir, f"{db_name}.{format}")

    if not split:
        db_tools.save_db(indices_data, os.path.join(output_dir, f"{db_name}.{format}"))

    db_tools.serialize(
        span_registry_file,
        {"type": db.SerializedDataType.SPAN_DEFINITION.value, "data": span_registry},
        sort_keys=True,
    )

    logger.info(f"Minimum storage required: {ByteCounter.auto(total_size)}")


def parse_span_list(path) -> list[int]:
    """Read a space-separated list of span IDs from a file."""
    with open(path) as f:
        tokens = f.read().split()
    try:
        spans = sorted(int(t) for t in tokens)
    except ValueError as e:
        raise ValueError(f"Invalid span ID in {path}: {e}")
    if not spans:
        raise ValueError(f"Span list is empty: {path}")
    return spans


def read_jsonl_header(filename: str) -> Optional[int]:
    """Return the ``k`` value from the JSONL header (first line), or None."""
    with open(filename) as f:
        line = f.readline().strip()
    if not line:
        return None
    try:
        json_line = json.loads(line)
        return json_line.get("k")
    except json.JSONDecodeError:
        logger.warning(f"Could not parse JSONL header in {filename}")
        return None


def stream_samples(filename: str) -> Generator[db.Sample, None, None]:
    """Yield Sample objects from a JSONL file, skipping the header line."""
    with open(filename) as f:
        f.readline()  # skip header
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                logger.warning(f"Could not parse JSONL entry: {line}")
                continue
            if "name" not in entry:
                continue
            files = entry.get("files", [])
            if not files:
                logger.warning(f"Sample {entry['name']} has no files, skipping")
                continue
            yield db.Sample(
                name=entry["name"],
                files=files,
                kmer_count=entry.get("kmer_count", 0),
            )


def prepare_sample(
    sample: db.Sample,
    db_tools: db.IndexDefinitionTools,
):
    logger.debug(f"Processing sample {sample.name or sample.files[0]}")

    sample_name = sample.name
    if not sample_name:
        filename = os.path.basename(sample.files[0])
        if filename.endswith((".gz", ".bz2", ".zip", ".xz")):
            filename = os.path.splitext(filename)[0]
        sample_name = os.path.splitext(filename)[0]

    sample_name = db_tools.clean_sample_id(sample.name)

    if sample_name != sample.name:
        logger.debug(
            f"    New sample ID: {sample_name}"
            + (f" (ex: {sample.name})" if sample.name else "")
        )
        if sample.name:
            sample.create_link(db.DbFields.ORIGINAL_ID, sample.name)
        sample.name = sample_name

    if not sample.name:
        raise ValueError("Sample ID empty or null")
    if sample.kmer_count <= 0:
        raise ValueError(f"Bad number of k-mers ({sample.kmer_count})")
