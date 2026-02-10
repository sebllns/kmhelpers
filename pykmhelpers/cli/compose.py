"""Compression commands for k-mer indices.

This module provides two approaches to index compression:
1. compress: Direct partition compression with advanced options (sampling, permutation, etc.)
2. kmindex-compress: Registry-based compression using the KmindexWrapper
"""

import os
import logging
import click
import pykmhelpers.pipeline.index_db as db
from pykmhelpers.core.bloom_filter import SpanManager, BloomFilterSpecs
from pykmhelpers.core.kmer import KmerCounter
from pykmhelpers.core.byte import ByteCounter, SizeFormat
from pykmhelpers.core.constants import KMHELPERS_VERSION

logger = logging.getLogger(__name__)


@click.command(name="compose")
@click.argument("input_files", nargs=-1, required=True, type=click.Path(exists=True))
@click.option(
    "--output-dir",
    "-o",
    required=True,
    type=click.Path(file_okay=False, dir_okay=True),
    help="Output directory for compressed index",
)
@click.option(
    "--prefix",
    default="span",
    help="Prefix for index names",
)
@click.option(
    "--name",
    "-n",
    default="db",
    help="Name of created index database",
)
@click.option(
    "--kmer-size",
    "-k",
    type=int,
    default=25,
    help="K-mer size (default: 25)",
)
@click.option(
    "--min-span",
    "-s",
    type=int,
    default=25,
    help="Minimum span, 0 for disabling min limit (default: 25)",
)
@click.option(
    "--max-span",
    "-S",
    type=int,
    default=0,
    help="Maximum span, 0 for disabling max limit (default: 0)",
)
@click.option(
    "--partition-count",
    "-p",
    type=int,
    default=0,
    help="Desired number of partitions per index, 0 for automatic count (default: 0)",
)
@click.option(
    "--bf-max-size",
    "-b",
    help="Maximum Bloom Filter size (e.g., '10GB', '5000MB') before splitting samples across indices (default = no limit)",
)
@click.option(
    "--partition-max-size",
    "-m",
    help="Maximum partition file size (e.g., '500MB', '1GB'). If exceeded, partition count will increase to maintain this size limit per partition (default = no limit)",
)
@click.option(
    "--no-merge",
    is_flag=True,
    default=False,
    help="Treat each part of split indices as independent indices (mostly used for partition count calculation)",
)
@click.option(
    "--exact-partition-count",
    is_flag=True,
    default=False,
    help="Keep exact partition count (default rounds to nearest power of 2)",
)
@click.option(
    "--partition-count-limit",
    type=int,
    default=256,
    help="Partition count limit for auto-partitioning (default: 256)",
)
@click.option(
    "--ntcard-threads",
    "--ntt",
    type=int,
    default=8,
    help="Number of threads to be used by ntcard while counting k-mers (default: 8)",
)
@click.option(
    "--ntcard-value",
    "--ntv",
    default="F0",
    help="Value ID to extract from ntcard output (default: 'F0')",
)
@click.option(
    "--false-positive-rate",
    "--fp",
    type=float,
    default=0.25,
    help="False positive rate for Bloom filter (default: 0.25).\n\n==>IMPORTANT<== The findere algorithm optimizes queries by using (k+z)-mers to reduce the false positive rate at query time. This allows Bloom filters to be built with a higher false positive rate while still providing accurate results, which reduces disk footprint. Usually building your index with {k=25, p=0.25} and querying with z=6 provide a good balance.\n\n ",
)
@click.option(
    "--no-split",
    is_flag=True,
    default=False,
    help="Export all index definition to a single file",
)
@click.option(
    "--recount",
    is_flag=True,
    default=False,
    help="Force recount k-mers for all samples (ignore cached kmer_count)",
)
@click.option(
    "--format",
    "-f",
    type=click.Choice(["yaml", "json"], case_sensitive=False),
    default="yaml",
    help="Output format of created database (default: 'yaml')",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    help="Increase log level to INFO (unless already higher)",
)
def compose(
    input_files,
    output_dir,
    prefix,
    name,
    kmer_size,
    min_span,
    max_span,
    partition_count,
    bf_max_size,
    partition_max_size,
    no_merge,
    exact_partition_count,
    partition_count_limit,
    ntcard_threads,
    ntcard_value,
    false_positive_rate,
    no_split,
    recount,
    format,
    verbose,
):
    """Compose index definition file(s) from list(s) of samples.

    Examples:
      kmhelpers compose -o ./db -k 31 samples.yaml
      kmhelpers compose -o ./db --min_span 25 --max_span 38 --split samples.yaml
      kmhelpers compose -o ./db --format json samples.yaml
      kmhelpers compose -o ./db --format yaml --split samples.yaml
      kmhelpers compose -o ./db -p 0.01 samples.yaml
      kmhelpers compose -o ./db --partition-count 4 samples.yaml
      kmhelpers compose -o ./db --recount samples.yaml
    """

    # Bump logging level to INFO if -v is set and current level is higher
    if verbose:
        root_logger = logging.getLogger()
        if root_logger.getEffectiveLevel() > logging.INFO:
            root_logger.setLevel(logging.INFO)
            # Also update all handlers
            for handler in root_logger.handlers:
                if handler.level > logging.INFO:
                    handler.setLevel(logging.INFO)

    try:
        # Validate parameters
        if kmer_size <= 0:
            raise click.BadParameter(
                f"Constraint must be respected: k > 0 (got k = {kmer_size})"
            )
        if kmer_size >= 64:
            raise click.BadParameter(
                f"Constraint must be respected: k < 64 (got k = {kmer_size})"
            )
        if min_span >= 30:
            raise click.BadParameter(
                f"Constraint must be respected: min_span < 30 (got min_span = {min_span})"
            )
        if max_span < 0:
            raise click.BadParameter(
                f"Constraint must be respected: max_span >= 0 (got max_span = {max_span})"
            )
        if max_span > 0 and max_span < min_span:
            raise click.BadParameter(
                f"Constraint must be respected: max_span >= min_span (got max_span = {max_span}, min_span = {min_span})"
            )
        if false_positive_rate <= 0:
            raise click.BadParameter(
                f"Constraint must be respected: false_positive_rate > 0 (got false_positive_rate = {false_positive_rate})"
            )
        if partition_count < 0:
            raise click.BadParameter(
                f"Constraint must be respected: partition_count >= 0 (got partition_count = {partition_count})"
            )

        auto_partitioning = False
        # Default partitioning = 256
        if partition_count == 0:
            auto_partitioning = True
            partition_count = 256

        try:
            bf_max_size = ByteCounter.from_str(bf_max_size) if bf_max_size else None
        except ValueError:
            raise click.BadParameter(
                f"Invalid bf_max_size format: {bf_max_size} (use format like '1GB', '500MB')"
            )

        try:
            partition_max_size = (
                ByteCounter.from_str(partition_max_size) if partition_max_size else None
            )
        except ValueError:
            raise click.BadParameter(
                f"Invalid partition_max_size format: {partition_max_size} (use format like '1GB', '500MB')"
            )

        os.makedirs(output_dir, exist_ok=True)
        all_samples = []
        split_count = {}
        span_size = {}
        db_instance = db.IndexTable()
        db_tools = db.IndexDefinitionTools()

        for input_file in input_files:
            samples = read_samples(input_file, kmer_size)
            all_samples.extend(samples)
            logger.info(f"Loaded {len(samples)} samples from {input_file}")

        logger.info(f"Total samples loaded: {len(all_samples)}")

        for sample in all_samples:
            try:
                span, bf_size = process_sample(
                    sample=sample,
                    db_tools=db_tools,
                    kmer_size=kmer_size,
                    min_span=min_span,
                    max_span=max_span,
                    ntcard_threads=ntcard_threads,
                    ntcard_value=ntcard_value,
                    false_positive_rate=false_positive_rate,
                    recount=recount,
                )

                if span not in split_count:
                    split_count[span] = 0

                if span not in span_size:
                    span_size[span] = 0

                index_id = f"{prefix}_{span}_{split_count[span]}"
                if index_id not in db_instance:
                    logger.info(
                        f"Creating new index: {index_id}, span={span}, bf_size={bf_size}"
                    )
                    db_instance[index_id] = db.Index(
                        id=index_id,
                        kmhelpers_version=KMHELPERS_VERSION,
                        kmer_size=kmer_size,
                        span=span,
                        bf_size=bf_size,
                        partition_count=partition_count,
                        samples={},
                    )
                else:
                    logger.info(f"Adding to existing index: {index_id}")

                db_instance[index_id].add_sample(sample_id=sample.id, sample=sample)
                span_size[span] += 1
                # Split index if needed
                if (
                    bf_max_size
                    and span_size[span] % 8 == 0
                    and bf_max_size <= db_instance[index_id].get_stored_size()
                ):
                    split_count[span] += 1

            except Exception as e:
                click.echo(
                    f"Could not process sample: {e}",
                    err=True,
                )

        logger.info(
            f"Composed {len(all_samples)} samples into {len(db_instance)} indices"
        )
        for index_id, index in sorted(db_instance.items()):
            logger.info(
                f"  {index_id}: {index.sample_count} samples, {str(index.get_stored_size())}"
            )
        logger.info(f"Exporting database in {format} format to {output_dir}...")

        for i in db_instance.values():
            if partition_max_size or auto_partitioning:
                partition_max_size = partition_max_size or ByteCounter.from_str("4GB")
                ref = db_instance[f"{prefix}_{i.span}_0"]
                bf_specs = BloomFilterSpecs(
                    ref.bf_size, ref.sample_count if no_merge else span_size[i.span], 1
                )
                partition_min_count = bf_specs.get_auto_partition_count(
                    partition_max_size.byte_count
                )
                if not auto_partitioning:
                    partition_min_count = max(partition_min_count, partition_count)
                i.partition_count = partition_min_count
            if not exact_partition_count and i.partition_count > 1:
                i.partition_count = 1 << (i.partition_count - 1).bit_length()

            i.partition_count = min(max(1, i.partition_count), partition_count_limit)
            logger.info(f"  {i.id}: partitioning into {i.partition_count} files")

        export_db(
            indices_data=db_instance,
            db_tools=db_tools,
            output_dir=output_dir,
            format=format,
            split=not no_split,
            db_name=name,
        )

        if not no_split:
            logger.info(f"Exported {len(db_instance)} index files (split mode)")
        else:
            logger.info(f"Exported database to db.{format}")
        logger.info(f"Created index definition for {len(all_samples)} samples")

    except Exception as e:
        raise click.ClickException(f"Compose failed: {e}")


def export_db(
    indices_data: db.IndexTable,
    db_tools: db.IndexDefinitionTools,
    output_dir: str,
    format: str,
    split: bool,
    db_name: str,
):
    """Export database to YAML or JSON format.

    Args:
        db_obj: IndexTable instance to export
        output_dir: Output directory path
        format: Export format ("yaml" or "json")
        split: If True, export each index to separate file; if False, export single file
    """
    os.makedirs(output_dir, exist_ok=True)

    format = format.lower()
    if format not in ("yaml", "json"):
        raise ValueError(f"Unsupported format: {format}. Must be 'yaml' or 'json'")

    # Export to file(s)
    if split:
        # Export each index to its own file
        for index_id, index_data in indices_data.items():
            filepath = os.path.join(output_dir, f"{db_name}_{index_id}.{format}")
            db_tools.save_db(db.IndexTable({index_id: index_data}), filepath)
    else:
        # Export all indices to a single file
        filepath = os.path.join(output_dir, f"{db_name}.{format}")
        db_tools.save_db(indices_data, filepath)


def read_samples(filename, cli_kmer_size=None):
    """Parse sample file in YAML, JSON, or plain text format.

    Supported formats:
    - YAML/JSON:
        k: 25
        samples:
          sample_000:
            kmer_count: 36564
            files:
            - samples/sample_000.fasta

    - Plain text (one sample per line):
        file_1[,file_2,...] [kmer_count]

    Returns:
        List of Sample objects with id, path (list), and kmer_count
    """
    import yaml
    import json

    samples = []

    if filename.endswith(".yaml") or filename.endswith(".yml"):
        with open(filename, "r") as f:
            data = yaml.safe_load(f)
            file_k = data.get("k")
            if file_k and cli_kmer_size and file_k != cli_kmer_size:
                logger.warning(
                    f"File k={file_k} does not match CLI k={cli_kmer_size}"
                )
            if "samples" in data:
                for sample_id, sample_data in data["samples"].items():
                    files = sample_data.get("files", [])
                    if not files:
                        logger.warning(
                            f"Sample {sample_id} has no files, skipping"
                        )
                        continue

                    kmer_count = sample_data.get("kmer_count", 0)

                    sample = db.Sample(id=sample_id, files=files, kmer_count=kmer_count)
                    samples.append(sample)

    elif filename.endswith(".json"):
        with open(filename, "r") as f:
            data = json.load(f)
            file_k = data.get("k")
            if file_k and cli_kmer_size and file_k != cli_kmer_size:
                logger.warning(
                    f"File k={file_k} does not match CLI k={cli_kmer_size}"
                )
            if "samples" in data:
                for sample_id, sample_data in data["samples"].items():
                    files = sample_data.get("files", [])
                    if not files:
                        logger.warning(
                            f"Sample {sample_id} has no files, skipping"
                        )
                        continue

                    kmer_count = sample_data.get("kmer_count", 0)

                    sample = db.Sample(id=sample_id, files=files, kmer_count=kmer_count)
                    samples.append(sample)

    else:
        # Plain text format: each line contains file paths and optional kmer count
        with open(filename, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                parts = line.split()
                files = []
                kmer_count = 0

                # Parse file paths and optional kmer_count
                for part in parts:
                    # Remove surrounding quotes if present
                    part = part.strip('"').strip("'")
                    try:
                        # Try to parse as integer (kmer_count)
                        kmer_count = int(part)
                    except ValueError:
                        # It's a file path
                        files.append(part)

                if files:
                    sample = db.Sample(id=None, files=files, kmer_count=kmer_count)
                    samples.append(sample)
    return samples


def process_sample(
    sample: db.Sample,
    db_tools: db.IndexDefinitionTools,
    kmer_size,
    min_span,
    max_span,
    ntcard_threads,
    ntcard_value,
    false_positive_rate,
    recount=False,
):
    logger.info(f"Processing sample {sample.id or sample.files[0]}")

    kc = KmerCounter(k=kmer_size, threadCount=ntcard_threads)
    sm = SpanManager(p=false_positive_rate)

    if sample.kmer_count == 0 or recount:
        action = "Recounting" if recount else "Counting"
        logger.info(f"  {action} k-mers for sample {sample.id or sample.files[0]}")
        sample.kmer_count = kc.count_files(
            files=sample.files, target_value=ntcard_value
        )
        logger.debug(f"    k-mer count: {sample.kmer_count}")
    else:
        logger.debug(
            f"  Using cached k-mer count for sample {sample.id or sample.files[0]}: {sample.kmer_count}"
        )

    span = sm.dispatch(sample.kmer_count)

    orig_span = span
    span = max(span, min_span)
    if max_span > 0:
        span = min(span, max_span)

    if span != orig_span:
        logger.debug(f"    Span adjusted: {orig_span} → {span}")

    bf_size = sm.get_bf_size(span)

    if not sample.id:
        filename = os.path.basename(sample.files[0])
        # Remove compression extensions (.gz, .bz2, .zip, etc.)
        if filename.endswith((".gz", ".bz2", ".zip", ".xz")):
            filename = os.path.splitext(filename)[0]
        # Remove file extension
        sample.id = os.path.splitext(filename)[0]
        logger.debug(f"    Generated sample ID from filename: {sample.id}")

    sample.id = db_tools.clean_sample_id(sample.id)
    logger.debug(f"    Final sample ID: {sample.id}")

    return span, bf_size
