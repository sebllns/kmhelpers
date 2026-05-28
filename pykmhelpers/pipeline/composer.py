"""Core composition logic for building index definition files from sample lists."""

import json
import logging
import os

import yaml

import pykmhelpers.pipeline.index_db as db
from pykmhelpers.core.bloom_filter import BloomFilterSpecs, SpanManager
from pykmhelpers.core.byte import ByteCounter
from pykmhelpers.core.constants import KMHELPERS_VERSION
from pykmhelpers.core.kmer import KmerCounter

logger = logging.getLogger(__name__)


def compose_indices(
    input_files,
    output_dir,
    prefix="span",
    name="index",
    kmer_size=25,
    assembled=True,
    allowed_spans=None,
    partition_count=0,
    bf_max_size=None,
    partition_min_size=None,
    no_merge=False,
    exact_partition_count=False,
    partition_count_limit=256,
    ntcard_threads=8,
    ntcard_value="F0",
    false_positive_rate=0.25,
    no_split=False,
    recount=False,
    format="yaml",
):
    """Compose index definition file(s) from lists of samples.

    Args:
        input_files: Iterable of input file paths.
        output_dir: Output directory for composed database files.
        prefix: Prefix for index names.
        name: Name of the created index database.
        kmer_size: K-mer size.
        assembled: True for assembled genomes, False for raw reads.
        allowed_spans: Sorted list of permitted span IDs, or None for no restriction.
        partition_count: Desired number of partitions per index (0 = auto).
        bf_max_size: ByteCounter max BF size before splitting, or None.
        partition_min_size: ByteCounter min partition size, or None.
        no_merge: Treat split index parts as independent indices.
        exact_partition_count: Keep exact partition count (no power-of-2 rounding).
        partition_count_limit: Upper bound on auto partition count.
        ntcard_threads: Threads for ntcard k-mer counting.
        ntcard_value: Value ID to extract from ntcard output.
        false_positive_rate: Bloom filter false-positive rate.
        no_split: Export all index definitions to a single file.
        recount: Force recount k-mers even if cached.
        format: Output format, "yaml" or "json".
    """
    auto_partitioning = partition_count == 0
    if auto_partitioning:
        partition_count = 256

    os.makedirs(output_dir, exist_ok=True)
    all_samples: list[db.Sample] = []
    split_count = {}
    original_distribution = {}
    bf_sizes = {}
    span_size = {}
    db_instance = db.IndexDB(name=name)
    db_tools = db.IndexDefinitionTools()
    sm = SpanManager(p=false_positive_rate)

    for input_file in input_files:
        samples = read_samples(input_file, kmer_size)
        all_samples.extend(samples)
        logger.info(f"Loaded {len(samples)} samples from {input_file}")

    logger.info(f"Total samples loaded: {len(all_samples)}")

    for sample in all_samples:
        try:
            assert sample.files and sample.files[0], "Invalid path: empty or null"
            prepare_sample(
                sample=sample,
                db_tools=db_tools,
                kmer_size=kmer_size,
                ntcard_threads=ntcard_threads,
                ntcard_value=ntcard_value,
                recount=recount,
            )

            span = sm.dispatch(sample.kmer_count)

            if allowed_spans:
                promoted = next((s for s in allowed_spans if s >= span), None)
                if promoted is None:
                    raise ValueError(
                        f"No allowed span >= {span} for sample '{sample.name}' "
                        f"(kmer_count={sample.kmer_count}). Extend the span list."
                    )
                span = promoted

            original_distribution[span] = original_distribution.get(span, 0) + 1

            bf_sizes[span] = sm.get_bf_size(span)

            if span not in split_count:
                split_count[span] = 0
            if span not in span_size:
                span_size[span] = 0

            index_name = db_tools.get_index_name(name, prefix, span, split_count[span])
            if index_name not in db_instance.index_table:
                logger.debug(
                    f"Creating new index: {index_name}, span={span}, bf_size={bf_sizes[span]}"
                )
                i = db.IndexDefinition(
                    name=index_name,
                    kmhelpers_version=KMHELPERS_VERSION,
                    kmer_size=kmer_size,
                    index_type="kmindex",
                    span=span,
                    bf_size=bf_sizes[span],
                    partition_count=partition_count,
                    assembled=assembled,
                    abundance_min=db_tools.get_abundance_min(assembled),
                    samples={},
                )
                if split_count[span] > 0 and not no_merge:
                    parent_name = db_tools.get_index_name(name, prefix, span, 0)
                    i.set_parent(parent_name)
                    assert (
                        parent_name in db_instance.index_table
                    ), f"Parent index not found: {parent_name}"
                    db_instance.index_table[parent_name].merge_name = (
                        db_tools.get_merge_name(name, prefix, span)
                    )

                i.merge_name = db_tools.get_merge_name(name, prefix, span)
                db_instance.add_index(i)
            else:
                logger.debug(f"Adding to existing index: {index_name}")

            assert sample.name, "Invalid ID: empty or null"
            db_instance.index_table[index_name].add_sample(
                sample_id=sample.name, sample=sample
            )

            span_size[span] += 1
            if (
                bf_max_size
                and span_size[span] % 8 == 0
                and bf_max_size <= db_instance.index_table[index_name].get_stored_size()
            ):
                split_count[span] += 1

        except Exception as e:
            logger.exception(
                f"Could not process sample '{sample.name}'({sample.id}): {e} ({type(e).__name__})"
            )

    logger.info(
        f"Composed {len(all_samples)} samples into {len(db_instance.index_table)} indices"
    )

    for index_name, index in sorted(db_instance.index_table.items()):
        logger.info(
            f"  {index_name} {index.sample_count} samples {str(index.get_stored_size())}"
        )

    original_distribution_file = os.path.join(output_dir, f"{name}_orig_dist.csv")
    with open(original_distribution_file, "w") as f:
        f.write("span,bf_size,sample_count\n")
        for span_id, sample_count in sorted(original_distribution.items()):
            f.write(f"{span_id},{bf_sizes[span_id]},{sample_count}\n")

    index_summary_file = os.path.join(output_dir, f"{name}_summary.csv")
    with open(index_summary_file, "w") as f:
        f.write("span,sample_count,stored_size_GB\n")
        for span_id, span_obj in sorted(db_instance.span_table.items()):
            size = span_obj.get_total_stored_size()
            f.write(
                f"{span_id},{span_obj.get_sample_count()},{size.byte_count/(1000**3)}\n"
            )

    logger.info(f"Exporting database in {format} format to {output_dir}...")

    for i in db_instance.index_table.values():
        if partition_min_size or auto_partitioning:
            partition_min_size = partition_min_size or ByteCounter.from_str("200MB")
            index_name = db_tools.get_index_name(name, prefix, i.span, 0)
            ref = db_instance.index_table[index_name]
            bf_specs = BloomFilterSpecs(
                ref.bf_size, ref.sample_count if no_merge else span_size[i.span], 1
            )
            partition_max_count = bf_specs.get_auto_partition_count(
                partition_min_size.byte_count
            )
            if not auto_partitioning:
                partition_max_count = min(partition_max_count, partition_count)
            i.partition_count = partition_max_count
        if not exact_partition_count and i.partition_count > 1:
            i.partition_count = 1 << (i.partition_count - 1).bit_length()

        i.partition_count = min(max(4, i.partition_count), partition_count_limit)
        logger.debug(f"  {i.name}: partitioning into {i.partition_count} files")

    export_db(
        indices_data=db_instance,
        db_tools=db_tools,
        output_dir=output_dir,
        format=format,
        split=not no_split,
        db_name=name,
    )

    logger.info(f"Exported database to {output_dir}")
    logger.info(f"Created index definition for {len(all_samples)} samples")


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

    logger.info(f"Estimated total index size: {ByteCounter.auto(total_size)}")


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


def read_samples(filename, cli_kmer_size=None) -> list[db.Sample]:
    """Parse a sample file in YAML, JSON, or plain-text format.

    Plain text (one sample per line):
        [sample_id] file_1[,file_2,...] [kmer_count]

    YAML/JSON:
        k: <integer>
        samples:
          <sample_id>:
            [kmer_count: <optional_integer>]
            files:
              - <path_to_file>
    """
    samples = []

    if filename.endswith((".yaml", ".yml")):
        with open(filename) as f:
            data = yaml.safe_load(f)
        file_k = data.get("k")
        if file_k and cli_kmer_size and file_k != cli_kmer_size:
            logger.warning(f"File k={file_k} does not match CLI k={cli_kmer_size}")
        for sample_id, sample_data in data.get("samples", {}).items():
            files = sample_data.get("files", [])
            if not files:
                logger.warning(f"Sample {sample_id} has no files, skipping")
                continue
            samples.append(
                db.Sample(
                    name=sample_id,
                    files=files,
                    kmer_count=sample_data.get("kmer_count", 0),
                )
            )

    elif filename.endswith(".json"):
        with open(filename) as f:
            data = json.load(f)
        file_k = data.get("k")
        if file_k and cli_kmer_size and file_k != cli_kmer_size:
            logger.warning(f"File k={file_k} does not match CLI k={cli_kmer_size}")
        for sample_id, sample_data in data.get("samples", {}).items():
            files = sample_data.get("files", [])
            if not files:
                logger.warning(f"Sample {sample_id} has no files, skipping")
                continue
            samples.append(
                db.Sample(
                    name=sample_id,
                    files=files,
                    kmer_count=sample_data.get("kmer_count", 0),
                )
            )

    else:
        # Plain text: [sample_id] file_1[,file_2,...] [kmer_count]
        with open(filename) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                parts = line.split()
                kmer_count = 0
                try:
                    kmer_count = int(parts[-1])
                    parts = parts[:-1]
                except ValueError:
                    pass

                if not parts:
                    logger.warning(
                        f"Invalid line format: {line}. "
                        "Expected: [sample_id] file_1[,file_2,...] [kmer_count]"
                    )
                    continue

                if len(parts) == 1:
                    sample_id = None
                    files_str = parts[0]
                else:
                    sample_id = parts[0]
                    files_str = " ".join(parts[1:])

                files = [f.strip().strip('"').strip("'") for f in files_str.split(",")]
                if files:
                    samples.append(
                        db.Sample(name=sample_id, files=files, kmer_count=kmer_count)
                    )

    return samples


def prepare_sample(
    sample: db.Sample,
    db_tools: db.IndexDefinitionTools,
    kmer_size: int,
    ntcard_threads: int,
    ntcard_value: str,
    recount: bool = False,
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

    assert sample.name, "Sample ID empty or null"

    kc = KmerCounter(k=kmer_size, threadCount=ntcard_threads)
    if sample.kmer_count == 0 or recount:
        action = "Recounting" if recount else "Counting"
        logger.info(f"  {action} k-mers for sample {sample.name}")
        sample.kmer_count = kc.count_files(
            files=sample.files, target_value=ntcard_value
        )
