"""Core composition logic for building index definition files from sample lists."""

import datetime
import json
import logging
import math
import os
import shutil
from typing import Generator, Optional

import yaml

import pykmhelpers.pipeline.index_db as db
from pykmhelpers.core.bloom_filter import SpanManager
from pykmhelpers.core.byte import ByteCounter
from pykmhelpers.core.constants import (
    DEFAULT_MINIM_SIZE,
    KMHELPERS_COMMIT,
    KMHELPERS_VERSION,
    SHARD_BUDGET,
)
from pykmhelpers.core.log import Log

logger = logging.getLogger(__name__)

# Files of COMPOSE_DIR/NAME/ (the index) and COMPOSE_DIR/NAME/SESSION/
LAYOUT_FILE = "layout.yaml"
SESSION_FILE = "index"  # + ".yaml" or ".json": the input of plan/apply/build
SESSION_SAMPLES = "samples.jsonl"
SESSION_SUMMARY = "summary.csv"
SHARDS_DIR = "shards"
# k-mer occurrences per counted k-mer of a sample whose list has no kmer_total
DEFAULT_KMER_RATIO_ASSEMBLED = 1.0
DEFAULT_KMER_RATIO_RAW = 4.0


def layout_path(compose_dir: str, name: str) -> str:
    """Layout of index ``name``: ``COMPOSE_DIR/NAME/layout.yaml``."""
    return os.path.join(compose_dir, name, LAYOUT_FILE)


class IndexComposer:

    def __init__(
        self,
        profiles_file=None,
        layout_file=None,
        selected_profile=None,
        name="index",
        abundance_min=1,
        bitw: Optional[int] = None,
        no_merge=False,
        shard_size: int = 0,
        shard_budget: Optional[int] = None,
        partition_count: int = 0,
        minim_size: Optional[int] = None,
        kmer_size: Optional[int] = None,
        false_positive_rate: Optional[float] = None,
        format="yaml",
        db_tools: Optional[db.IndexDefinitionTools] = None,
        copy_list: bool = True,
        kmer_ratio: float = 1.0,
    ):
        self.profiles_file = profiles_file
        self.layout_file = layout_file
        self.selected_profile = selected_profile
        self.name = name or "index"
        self.abundance_min = abundance_min
        # None: the layout's value on an update, presence/absence (0) otherwise
        self.bitw = None if bitw is None else max(bitw, 0)
        self.no_merge = no_merge
        if shard_size and shard_budget is not None:
            raise ValueError("A shard is capped by a budget or by a size, not both")
        # The shard rule, one of: a byte size (shard_size), or a budget of
        # samples * base**span (shard_budget). Neither: the layout's rule on an
        # update, SHARD_BUDGET otherwise
        self.shard_size = shard_size
        self.shard_budget = shard_budget
        self.partition_count = partition_count
        # None: the layout's value on an update, DEFAULT_MINIM_SIZE otherwise
        self.minim_size = minim_size
        self.kmer_size = kmer_size
        self.false_positive_rate = false_positive_rate
        self.format = format
        self.db_tools = db_tools or db.IndexDefinitionTools()
        # False: the shards point to the input sample list instead of a copy
        # in the session, so the list must stay in place and unchanged
        self.copy_list = copy_list
        if kmer_ratio <= 0:
            raise ValueError(f"k-mer ratio must be positive, got {kmer_ratio}")
        # Multiplies the k-mer ratio computed from the sample list
        self.kmer_ratio = kmer_ratio

    def _session_sample_file(
        self, input_file: str, output_dir: str, run_dir: str
    ) -> str:
        """The sample list of the session, as ``sample_file`` of its shards.

        Copied to SESSION/samples.jsonl by default. Without the copy, the input
        list itself: relative to SESSION/shards/ when it lies in the parent of
        ``output_dir`` (the design directory, which can then move as a whole),
        absolute otherwise.
        """
        session_copy = os.path.join(run_dir, SESSION_SAMPLES)
        if self.copy_list:
            try:
                shutil.copy(input_file, session_copy)
            except shutil.SameFileError:
                pass
            # shards/<shard>.yaml -> SESSION/samples.jsonl
            return f"../{SESSION_SAMPLES}"

        input_file = os.path.realpath(input_file)
        if os.path.realpath(session_copy) != input_file and os.path.isfile(session_copy):
            # left by an earlier run of the session: no longer used
            os.remove(session_copy)
        root = os.path.dirname(os.path.realpath(output_dir))
        if os.path.commonpath([root, input_file]) == root:
            return os.path.relpath(input_file, os.path.join(run_dir, SHARDS_DIR))
        return input_file

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
        # The hard min the k-mers were counted with (2 for raw reads)
        abundance_min = (
            read_jsonl_abundance_min(input_file) or self.abundance_min
        )
        default_ratio = (
            DEFAULT_KMER_RATIO_ASSEMBLED
            if read_jsonl_assembled(input_file)
            else DEFAULT_KMER_RATIO_RAW
        )
        # Largest occurrences / counted k-mers of the samples of each definition
        sample_ratios: dict[str, float] = {}
        file_fp = None

        span_base = 2.0
        allowed_spans: list[int] = []
        spans_properties: dict[int, dict] = {}

        run_id = run_id or datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

        logger.info(f"Run ID: {run_id}")

        run_dir = os.path.realpath(os.path.join(output_dir, self.name, run_id))
        os.makedirs(run_dir, exist_ok=True)

        sample_file = self._session_sample_file(input_file, output_dir, run_dir)

        shard_size = 0
        minim_size = 0
        out_layout = None
        sessions: list[str] = []
        layout_budget = 0

        if self.layout_file:
            span_base, shard_size, minim_size, spans_properties = load_layout(
                self.layout_file
            )
            allowed_spans = sorted(spans_properties.keys())
            out_layout = os.path.realpath(self.layout_file)
            sessions = load_layout_sessions(self.layout_file)
            layout_budget = load_layout_shard_budget(self.layout_file)
            if self.minim_size is None:
                # Layouts written before it was set at design: the default
                self.minim_size = minim_size or DEFAULT_MINIM_SIZE
            elif minim_size and minim_size != self.minim_size:
                raise ValueError(
                    f"Layout {self.layout_file} was composed with minimizer size "
                    f"{minim_size}, got {self.minim_size}: indexes with different "
                    "minimizer sizes cannot be merged"
                )
            layout_bitw = load_layout_bitw(self.layout_file)
            if self.bitw is None:
                self.bitw = layout_bitw
            elif layout_bitw != self.bitw:
                raise ValueError(
                    f"Layout {self.layout_file} was composed with bitw={layout_bitw}, "
                    f"got bitw={self.bitw}: presence/absence and abundance indexes "
                    "cannot be merged"
                )
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
            out_layout = os.path.realpath(layout_path(output_dir, self.name))

        if self.bitw is None:
            self.bitw = 0
        if self.minim_size is None:
            self.minim_size = DEFAULT_MINIM_SIZE
        minim_size = self.minim_size

        # An update keeps the layout's shard rule unless one is passed again
        updating = bool(self.layout_file and not self.profiles_file)
        layout_rule = (layout_budget, shard_size)
        if self.shard_size:
            self.shard_budget = 0
        elif self.shard_budget is not None:
            self.shard_size = 0
        elif updating:
            self.shard_budget, self.shard_size = layout_rule
        else:
            self.shard_budget, self.shard_size = SHARD_BUDGET, 0
        reshard = updating and (self.shard_budget, self.shard_size) != layout_rule
        shard_size = self.shard_size

        kmer_size = self.kmer_size or file_k or 25
        if minim_size >= kmer_size:
            raise ValueError(
                f"Minimizer size ({minim_size}) must be smaller than k ({kmer_size})"
            )
        false_positive_rate = self.false_positive_rate or file_fp or 0.25

        original_distribution: dict[int, int] = {}
        bf_sizes: dict[int, int] = {}
        db_instance = db_instance or db.IndexDB(name=self.name)
        span_manager = span_manager or SpanManager(p=false_positive_rate, b=span_base)

        if self.profiles_file:
            spans_properties = self._fill_span_props(
                allowed_spans, span_manager, span_base, shard_size
            )
        elif reshard:
            # A layout can be re-sharded: only shards opened later are affected
            for span, props in spans_properties.items():
                props["max_samples"] = self._max_samples(
                    span, span_manager, span_base, shard_size
                )
            logger.info(f"Layout re-sharded ({self._shard_rule()})")

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
                shard = self._current_shard(props)

                index_name = self.db_tools.get_part_name(shard["name"], run_id)
                if index_name not in db_instance.index_table:
                    logger.debug(
                        f"Creating new index: {index_name}, span={span}, bf_size={bf_sizes[span]}"
                    )
                    i = db.IndexDefinition(
                        name=index_name,
                        kmhelpers_version=KMHELPERS_VERSION,
                        kmhelpers_commit=KMHELPERS_COMMIT,
                        kmer_size=kmer_size,
                        index_type="kmindex-abundance" if self.bitw else "kmindex",
                        span=span,
                        bf_size=bf_sizes[span],
                        abundance_min=abundance_min,
                        bitw=self.bitw,
                        minim_size=minim_size,
                        sample_file=sample_file,
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
                # At least 1: ntcard estimates kmer_count, which can exceed
                # the occurrences of a small sample
                ratio = (
                    max(1.0, sample.kmer_total / sample.kmer_count)
                    if sample.kmer_total
                    else default_ratio
                )
                sample_ratios[index_name] = max(
                    sample_ratios.get(index_name, 0.0), ratio
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

        for index_name, ratio in sample_ratios.items():
            db_instance.index_table[index_name].kmer_ratio = round(
                self.kmer_ratio * ratio, 2
            )

        logger.info(
            f"Composed {sample_count} samples into {len(db_instance.index_table)} "
            f"parts over {len(db_instance.span_table)} spans"
        )
        for i in db_instance.index_table.values():
            logger.info(
                f"  {i.merge_name}: {i.sample_count} samples → {str(i.get_stored_size())}"
            )

        with open(os.path.join(run_dir, SESSION_SUMMARY), "w") as f:
            f.write("shard,span,bf_size,samples,size_GB\n")
            for i in sorted(db_instance.index_table.values(), key=lambda i: i.span):
                size = i.get_stored_size()
                f.write(
                    f"{i.merge_name},{i.span},{i.bf_size},{i.sample_count},"
                    f"{size.byte_count/(1000**3)}\n"
                )

        logger.debug(f"Exporting database in {self.format} format to {run_dir}...")

        session_file = export_session(
            indices_data=db_instance,
            db_tools=self.db_tools,
            output_dir=run_dir,
            format=self.format,
            index_name=self.name,
            session=run_id,
            distribution=original_distribution,
        )

        logger.info(f"Exported session definition: {session_file}")

        if out_layout:
            if run_id not in sessions:
                sessions.append(run_id)
            self._write_layout(
                out_layout,
                span_base,
                shard_size,
                minim_size,
                spans_properties,
                sessions,
            )

    def _fill_span_props(
        self,
        allowed_spans: list[int],
        span_manager: SpanManager,
        span_base: float,
        shard_size: int,
    ) -> dict:
        """Per-span properties of a new index: name, sample limits, shards."""
        props = {}
        for i, span in enumerate(allowed_spans):
            props[span] = {
                "id": i,
                "name": self.db_tools.get_merge_name(self.name, i),
                "max_samples": self._max_samples(
                    span, span_manager, span_base, shard_size
                ),
                "total_samples": 0,
                "updates": -1,
                "partition_count": 0,
                "shards": [],
            }
        return props

    def _max_samples(
        self, span: int, span_manager: SpanManager, span_base: float, shard_size: int
    ) -> int:
        """Samples one shard of ``span`` holds, 0 meaning unlimited.

        Capped by ``shard_size`` bytes when set, else by the shard budget.
        """
        if shard_size:
            return max_samples_for(
                span_manager.get_bf_size(span), shard_size, self.bitw or 0
            )
        return budget_samples_for(span, span_base, self.shard_budget or 0)

    def _shard_rule(self) -> str:
        """The shard rule, for logs."""
        if self.shard_size:
            return f"shard size: {ByteCounter.auto(self.shard_size)}"
        return f"shard budget: {self.shard_budget or 'no limit'}"

    def _current_shard(self, props: dict) -> dict:
        """Shard receiving the next sample: the last one, or a new one if full."""
        shards = props["shards"]
        max_samples = props["max_samples"]
        if not shards or (max_samples and shards[-1]["samples"] >= max_samples):
            # Without sharding a span holds one unlimited index, named without suffix
            shard_id = len(shards) if max_samples else None
            # Derived from the span's recorded name, so a shard never drifts
            # from it (the group ordinal only ever mints that name)
            name = self.db_tools.get_shard_name(props["name"], shard_id)
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
        sessions: Optional[list[str]] = None,
    ) -> None:
        """Write the layout: shard state, build invariants of later sessions,
        and the sessions composed so far (the last one is built by default)."""
        layout_data = {
            "type": "layout",
            "data": {
                "base": span_base,
                "shard_size": shard_size,
                "minim_size": minim_size,
                "bitw": self.bitw,
                "shard_budget": self.shard_budget or 0,
                "sessions": list(sessions or []),
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


def max_samples_for(bf_size: int, shard_size: int, bitw: int = 0) -> int:
    """Samples a shard of at most ``shard_size`` bytes can hold, 0 if unlimited.

    A shard stores one Bloom filter row per k-mer slot and one bit column per
    sample (``bitw`` bits for an abundance index), so it costs about
    ``bf_size * samples * bitw / 8`` bytes. Rows are byte
    aligned, hence the rounding down to a multiple of 8 samples. A shard holds
    at least 8 samples, so it may exceed ``shard_size`` when 8 do not fit.
    """
    if not shard_size or not bf_size:
        return 0
    return max(8, (8 * shard_size // (bf_size * max(bitw, 1))) // 8 * 8)


def budget_samples_for(span: int, base: float, budget: int) -> int:
    """Samples of ``span`` that fit a k-mer ``budget``, 0 if unlimited.

    Model from Logan: ``budget / base**span`` samples, rounded up to a
    multiple of 8. Sizes a shard (design ``--shard-budget``) and a kmtricks
    chunk (plan ``--chunk-budget``).
    """
    if not budget:
        return 0
    return max(8, math.ceil(budget / base**span / 8) * 8)


def load_layout_shard_budget(path: str) -> int:
    """Shard budget stored in a layout, 0 when unlimited or capped by size.

    Layouts written with the chunk model store ``chunk_budget`` and
    ``shard_chunks`` instead: their product is the shard budget. Older
    layouts have none: no limit.
    """
    with open(path) as f:
        data = yaml.safe_load(f).get("data", {})
    if data.get("shard_size"):
        return 0
    if "shard_budget" in data:
        return int(data["shard_budget"] or 0)
    return int(data.get("chunk_budget") or 0) * int(data.get("shard_chunks") or 64)


def load_layout_sessions(path: str) -> list[str]:
    """Sessions composed into a layout, oldest first."""
    with open(path) as f:
        data = yaml.safe_load(f)
    return [str(s) for s in data.get("data", {}).get("sessions") or []]


def load_layout_bitw(path: str) -> int:
    """Bits per abundance cell stored in a layout, 0 for presence/absence.

    Layouts written before abundance indexes have no ``bitw`` and are read as
    presence/absence.
    """
    with open(path) as f:
        data = yaml.safe_load(f)
    return int(data.get("data", {}).get("bitw") or 0)


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
        for i, (span, raw) in enumerate(sorted(payload["map"].items())):
            # A span mapped to a plain name predates sharding
            entry: dict = {"name": raw} if isinstance(raw, str) else dict(raw)
            stored_shards: list[dict] = list(entry.get("shards") or [])
            max_samples = int(entry.get("max_samples") or 0)
            shards = [
                {
                    "id": n if max_samples else None,
                    "name": sh["name"],
                    "samples": int(sh.get("samples", 0)),
                }
                for n, sh in enumerate(stored_shards)
            ]
            props[int(span)] = {
                "id": i,
                "name": entry["name"],
                "max_samples": max_samples,
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


def export_session(
    indices_data: db.IndexDB,
    db_tools: db.IndexDefinitionTools,
    output_dir: str,
    format: str,
    index_name: str,
    session: str,
    distribution: Optional[dict[int, int]] = None,
) -> str:
    """Write the definition of one session of an index, and return its path.

    ``SESSION/index.<format>`` (the input of plan/apply/build) describes the
    session: parameters, size, and the shards it adds samples to. Each shard's
    definition is written to ``SESSION/shards/<shard>.<format>``.
    """
    format = format.lower()
    if format not in ("yaml", "json"):
        raise ValueError(f"Unsupported format: {format}. Must be 'yaml' or 'json'")

    shards_dir = os.path.join(output_dir, SHARDS_DIR)
    os.makedirs(shards_dir, exist_ok=True)

    definitions = sorted(indices_data.index_table.values(), key=lambda i: i.span)
    shards: dict[str, dict] = {}
    total_size = 0
    for i in definitions:
        shard = i.merge_name or i.name
        assert shard and i.name
        size = i.get_stored_size()
        total_size += size.byte_count
        shard_file = f"{SHARDS_DIR}/{shard}.{format}"
        db_tools.save_db(
            db.IndexDB(name=i.name, index_table={i.name: i}),
            os.path.join(output_dir, shard_file),
        )
        shards[shard] = {
            "samples": i.sample_count,
            "size": str(size),
            "span": i.span,
            "bf_size": i.bf_size,
            "partitions": i.partition_count,
            "kmer_ratio": i.kmer_ratio,
            "file": shard_file,
        }

    first = definitions[0] if definitions else None
    sample_count = sum(i.sample_count for i in definitions)
    data = {
        "type": db.SerializedDataType.INDEX_SESSION.value,
        "index": index_name,
        "session": session,
        "kmhelpers": {"version": KMHELPERS_VERSION, "commit": KMHELPERS_COMMIT},
        "parameters": (
            {
                "kmer_size": first.kmer_size,
                "bitw": first.bitw,
                "minim_size": first.minim_size,
                "abundance_min": first.abundance_min,
                "fp_rate": first.fp_rate,
            }
            if first
            else {}
        ),
        "total": {"samples": sample_count, "size": str(ByteCounter.auto(total_size))},
        "distribution": dict(sorted((distribution or {}).items())),
        "shards": shards,
    }

    path = os.path.join(output_dir, f"{SESSION_FILE}.{format}")
    db_tools.serialize(path, data)
    if format == "yaml":
        header = (
            f"# {index_name}, session \"{session}\": {sample_count} samples "
            f"in {len(shards)} shard(s).\n"
            f"# Input of kmhelpers plan/apply/build: this file, or the design "
            f"(or compose) directory with -s {session}.\n"
        )
        with open(path) as f:
            body = f.read()
        with open(path, "w") as f:
            f.write(header + body)

    logger.info(f"Minimum storage required: {ByteCounter.auto(total_size)}")
    return path


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


def read_jsonl_abundance_min(filename: str) -> Optional[int]:
    """Return the ``abundance_min`` value from the JSONL header, or None."""
    with open(filename) as f:
        line = f.readline().strip()
    if not line:
        return None
    try:
        return json.loads(line).get("abundance_min")
    except json.JSONDecodeError:
        logger.warning(f"Could not parse JSONL header in {filename}")
        return None


def read_jsonl_assembled(filename: str) -> bool:
    """Return the ``assembled`` flag of the JSONL header, True when missing."""
    with open(filename) as f:
        line = f.readline().strip()
    if not line:
        return True
    try:
        return bool(json.loads(line).get("assembled", True))
    except json.JSONDecodeError:
        logger.warning(f"Could not parse JSONL header in {filename}")
        return True


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
                kmer_total=entry.get("kmer_total", 0),
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
