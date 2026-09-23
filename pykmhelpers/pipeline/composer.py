"""Core composition logic for building index definition files from sample lists."""

import datetime
import json
import logging
import os
import shutil
from typing import Generator, Optional

import yaml

import pykmhelpers.pipeline.index_db as db
from pykmhelpers.core.bloom_filter import SpanManager
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
        no_merge=False,
        shard_size: int = 0,
        partition_count: int = 0,
        kmer_size: Optional[int] = None,
        false_positive_rate: Optional[float] = None,
        format="yaml",
        db_tools: Optional[db.IndexDefinitionTools] = None,
    ):
        self.profiles_file = profiles_file
        self.layout_file = layout_file
        self.selected_profile = selected_profile
        self.name = name or "index"
        self.abundance_min = abundance_min
        self.no_merge = no_merge
        self.shard_size = shard_size
        self.partition_count = partition_count
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
        spans_properties: dict[int, dict] = {}

        run_id = run_id or datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

        logger.info(f"Run ID: {run_id}")

        run_dir = os.path.realpath(os.path.join(output_dir, self.name, run_id))
        os.makedirs(run_dir, exist_ok=True)

        try:
            shutil.copy(input_file, os.path.join(run_dir, f"{self.name}_samples.jsonl"))
        except shutil.SameFileError:
            pass

        shard_size = self.shard_size
        minim_size = 0
        out_layout = None

        if self.layout_file:
            span_base, shard_size, minim_size, spans_properties = load_layout(
                self.layout_file
            )
            allowed_spans = sorted(spans_properties.keys())
            out_layout = os.path.realpath(self.layout_file)
            logger.debug(
                f"Loaded layout: {self.layout_file} (base={span_base}, "
                f"spans={allowed_spans}, shard_size={shard_size})"
            )

        if self.profiles_file:
            file_fp, span_base, profile = load_profile(
                self.profiles_file, self.selected_profile
            )
            if not profile.get("span_list"):
                raise ValueError(f"Profile has no 'span_list' in {self.profiles_file}")
            allowed_spans = sorted(int(s) for s in profile["span_list"])
            out_layout = os.path.realpath(
                os.path.join(output_dir, f"{self.name}_layout.yaml")
            )

        kmer_size = self.kmer_size or file_k or 25
        false_positive_rate = self.false_positive_rate or file_fp or 0.25

        original_distribution: dict[int, int] = {}
        bf_sizes: dict[int, int] = {}
        db_instance = db_instance or db.IndexDB(name=self.name)
        span_manager = span_manager or SpanManager(p=false_positive_rate, b=span_base)

        if self.profiles_file:
            spans_properties = self._fill_span_props(
                allowed_spans, span_manager, shard_size
            )
        elif self.shard_size and self.shard_size != shard_size:
            # A layout can be re-sharded: only shards opened later are affected
            shard_size = self.shard_size
            for span, props in spans_properties.items():
                props["max_samples"] = max_samples_for(
                    span_manager.get_bf_size(span), shard_size
                )
            logger.info(
                f"Layout re-sharded with a {ByteCounter.auto(shard_size)} limit"
            )

        if self.partition_count:
            # Fixed by the user: every shard of the index keeps this count
            for props in spans_properties.values():
                props["partition_count"] = self.partition_count
            logger.info(f"Partition count fixed to {self.partition_count}")

        touched: set[int] = set()
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

                props = spans_properties[span]
                touched.add(span)
                shard = self._current_shard(props, shard_size)

                index_name = self.db_tools.get_index_name(
                    self.name, run_id, span, shard["id"]
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
                        abundance_min=self.abundance_min,
                        sample_file=f"{self.name}_samples.jsonl",
                        samples={},
                        partition_count=props.get("partition_count") or 0,
                    )
                    i.merge_name = shard["name"]
                    db_instance.add_index(i)
                else:
                    logger.debug(f"Adding to existing index: {index_name}")

                if not sample.name:
                    raise ValueError("Invalid ID: empty or null")
                db_instance.index_table[index_name].add_sample(
                    sample_id=sample.name, sample=sample
                )

                shard["samples"] += 1
                props["total_samples"] += 1
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

        for span in touched:
            spans_properties[span]["updates"] += 1

        logger.info(
            f"Composed {sample_count} samples into {len(db_instance.index_table)} "
            f"parts over {len(db_instance.span_table)} spans"
        )
        for i in db_instance.index_table.values():
            logger.info(
                f"  {i.merge_name}: {i.sample_count} samples → {str(i.get_stored_size())}"
            )

        original_distribution_file = os.path.join(run_dir, f"{self.name}_orig_dist.csv")
        with open(original_distribution_file, "w") as f:
            f.write("span,bf_size,sample_count\n")
            for span_id, count in sorted(original_distribution.items()):
                f.write(f"{span_id},{bf_sizes[span_id]},{count}\n")

        index_summary_file = os.path.join(run_dir, f"{self.name}_summary.csv")
        with open(index_summary_file, "w") as f:
            f.write("name,span,sample_count,stored_size_GB\n")
            for i in db_instance.index_table.values():
                size = i.get_stored_size()
                f.write(
                    f"{i.merge_name},{i.span},{i.sample_count},{size.byte_count/(1000**3)}\n"
                )

        logger.debug(f"Exporting database in {self.format} format to {run_dir}...")

        export_db(
            indices_data=db_instance,
            db_tools=self.db_tools,
            output_dir=run_dir,
            format=self.format,
            split=True,
            db_name=self.name,
        )

        logger.info(f"Exported database to {run_dir}")

        if out_layout:
            self._write_layout(
                out_layout, span_base, shard_size, minim_size, spans_properties
            )

    def _fill_span_props(
        self, allowed_spans: list[int], span_manager: SpanManager, shard_size: int
    ) -> dict:
        """Per-span properties of a new index: name, sample limit, shards."""
        props = {}
        for i, span in enumerate(allowed_spans):
            max_samples = max_samples_for(span_manager.get_bf_size(span), shard_size)
            props[span] = {
                "id": i,
                "name": self.db_tools.get_merge_name(self.name, i),
                "max_samples": max_samples,
                "total_samples": 0,
                "updates": -1,
                "partition_count": 0,
                "shards": [],
            }
        return props

    def _current_shard(self, props: dict, shard_size: int) -> dict:
        """Shard receiving the next sample: the last one, or a new one if full."""
        shards = props["shards"]
        max_samples = props["max_samples"]
        if not shards or (max_samples and shards[-1]["samples"] >= max_samples):
            # Without sharding a span holds one unlimited index, named without suffix
            shard_id = len(shards) if shard_size else None
            name = self.db_tools.get_merge_name(self.name, props["id"], shard_id)
            shards.append({"id": shard_id, "name": name, "samples": 0})
            if shard_id:
                logger.debug(
                    f"Shard {shards[-2]['name']} is full ({max_samples} samples), "
                    f"starting {name}"
                )
        current: dict = shards[-1]
        return current

    def _write_layout(
        self,
        path: str,
        span_base: float,
        shard_size: int,
        minim_size: int,
        spans_properties: dict,
    ) -> None:
        """Write the layout: shard state and build invariants of later sessions."""
        layout_data = {
            "type": "layout",
            "data": {
                "base": span_base,
                "shard_size": shard_size,
                "minim_size": minim_size,
                "map": {
                    span: {
                        "name": props["name"],
                        "max_samples": props["max_samples"],
                        "total_samples": props["total_samples"],
                        "updates": props["updates"],
                        "partition_count": props["partition_count"],
                        "shards": [
                            {"name": sh["name"], "samples": sh["samples"]}
                            for sh in props["shards"]
                        ],
                    }
                    for span, props in sorted(spans_properties.items())
                },
            },
        }
        with open(path, "w") as f:
            yaml.dump(layout_data, f, default_flow_style=False, sort_keys=True)
        logger.info(f"Wrote layout: {path}")


def max_samples_for(bf_size: int, shard_size: int) -> int:
    """Samples a shard of at most ``shard_size`` bytes can hold, 0 if unlimited.

    A shard stores one Bloom filter row per k-mer slot and one bit column per
    sample, so it costs about ``bf_size * samples / 8`` bytes. Rows are byte
    aligned, hence the rounding down to a multiple of 8 samples.
    """
    if not shard_size or not bf_size:
        return 0
    return max(8, (8 * shard_size // bf_size) // 8 * 8)


def load_layout(path: str) -> tuple[float, int, int, dict]:
    """Load ``(span_base, shard_size, minim_size, spans_properties)`` from a layout.

    Layouts written before sharding map a span to a plain index name; they are
    read as one unlimited shard, so existing indexes keep their names.
    """
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
        if data.get("type") != "layout":
            raise ValueError(f"Not a layout file: {path}")
        payload = data.get("data", {})
        base = float(payload["base"])
        if "map" not in payload:
            raise ValueError(f"Missing 'map' in layout file: {path}")

        shard_size = int(payload.get("shard_size") or 0)
        minim_size = int(payload.get("minim_size") or 0)
        props = {}
        for i, (span, entry) in enumerate(sorted(payload["map"].items())):
            if isinstance(entry, str):
                entry = {"name": entry}
            shards = [
                {
                    "id": n if shard_size else None,
                    "name": sh["name"],
                    "samples": int(sh.get("samples", 0)),
                }
                for n, sh in enumerate(entry.get("shards") or [])
            ]
            props[int(span)] = {
                "id": i,
                "name": entry["name"],
                "max_samples": int(entry.get("max_samples") or 0),
                "total_samples": int(entry.get("total_samples") or 0),
                "updates": int(entry.get("updates") or 0),
                "partition_count": int(entry.get("partition_count") or 0),
                "shards": shards,
            }
        return base, shard_size, minim_size, props
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
