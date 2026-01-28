"""Compression commands for k-mer indices.

This module provides two approaches to index compression:
1. compress: Direct partition compression with advanced options (sampling, permutation, etc.)
2. kmindex-compress: Registry-based compression using the KmindexWrapper
"""

import os
import click
import yaml
import json
import math
import pykmhelpers.pipeline.index_db as db
from pykmhelpers.core.bloom_filter import SpanManager, BloomFilterSpecs
from pykmhelpers.core.kmer import KmerCounter
from pykmhelpers.core.byte import ByteCounter, SizeFormat


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
    "--kmer-size",
    "-k",
    type=int,
    default=25,
    help="K-mer size (default: 25)",
)
@click.option(
    "--min-span",
    type=int,
    default=25,
    help="Minimum span, 0 for disabling min limit (default: 25)",
)
@click.option(
    "--max-span",
    type=int,
    default=0,
    help="Maximum span, 0 for disabling max limit (default: 0)",
)
@click.option(
    "--partition-count",
    type=int,
    default=0,
    help="Number of partitions per index, 0 for automatic count (default: 0)",
)
@click.option(
    "--ntcard-threads",
    type=int,
    default=8,
    help="Number of threads to be used by ntcard while counting k-mers (default: 8)",
)
@click.option(
    "--false-positive-rate",
    "-p",
    type=float,
    default=0.25,
    help="False positive rate for Bloom filter (default: 0.25)",
)
@click.option(
    "--split",
    is_flag=True,
    default=False,
    help="Split samples",
)
@click.option(
    "--recount",
    is_flag=True,
    default=False,
    help="Force recount k-mers for all samples (ignore cached kmer_count)",
)
@click.option(
    "--format",
    type=click.Choice(["yaml", "json"], case_sensitive=False),
    default="yaml",
    help="Output format (default: yaml)",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Verbose output",
)
def compose(
    input_files,
    output_dir,
    prefix,
    kmer_size,
    min_span,
    max_span,
    partition_count,
    ntcard_threads,
    false_positive_rate,
    split,
    recount,
    format,
    verbose,
):
    """Compose list of samples into input db for indexing

    Examples:
      kmhelpers compose -o ./db -k 31 samples.yaml
      kmhelpers compose -o ./db --min_span 25 --max_span 38 --split samples.yaml
      kmhelpers compose -o ./db --format json samples.yaml
      kmhelpers compose -o ./db --format yaml --split samples.yaml
      kmhelpers compose -o ./db -p 0.01 samples.yaml
      kmhelpers compose -o ./db --partition-count 4 samples.yaml
      kmhelpers compose -o ./db --recount samples.yaml
    """

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

        # Default partitioning = 256
        if partition_count == 0:
            partition_count = 256

        os.makedirs(output_dir, exist_ok=True)
        all_samples = []
        db_instance = db.IndexTable(indices={})

        for input_file in input_files:
            samples = read_samples(input_file, kmer_size)
            all_samples.extend(samples)
            if verbose:
                click.echo(f"Loaded {len(samples)} samples from {input_file}")

        if verbose:
            click.echo(f"Total samples loaded: {len(all_samples)}")

        for sample in all_samples:
            try:
                span, bf_size = process_sample(
                    sample, kmer_size, ntcard_threads, false_positive_rate, verbose, recount
                )

                orig_span = span
                span = max(span, min_span)
                if max_span > 0:
                    span = min(span, max_span)

                if verbose and span != orig_span:
                    click.echo(f"    Span adjusted: {orig_span} → {span}")

                index_id = f"{prefix}_{span}"
                if index_id not in db_instance.indices:
                    if verbose:
                        click.echo(f"  Creating new index: {index_id}")
                    db_instance.indices[index_id] = db.Index(
                        id=index_id,
                        bf_size=bf_size,
                        partition_count=partition_count,
                        stored_size_bytes=0,
                        stored_size_str="",
                        sample_count=0,
                        samples={},
                    )
                else:
                    if verbose:
                        click.echo(f"  Adding to existing index: {index_id}")

                db_instance.indices[index_id].samples[sample.id] = sample
                db_instance.indices[index_id].sample_count = len(
                    db_instance.indices[index_id].samples
                )
                bf_specs = BloomFilterSpecs(
                    bf_size, db_instance.indices[index_id].sample_count
                )
                db_instance.indices[index_id].stored_size_bytes = (
                    bf_specs.total_byte_count
                )
                db_instance.indices[index_id].stored_size_str = str(
                    ByteCounter.auto(bf_specs.total_byte_count, SizeFormat.BYTE)
                )
            except Exception as e:
                click.echo(
                    f"Could not process sample: {e}",
                    err=True,
                )

        if verbose:
            click.echo(f"✓ Composed {len(all_samples)} samples into {len(db_instance.indices)} indices")
            for index_id, index in db_instance.indices.items():
                click.echo(f"  {index_id}: {index.sample_count} samples, {index.stored_size_str}")
            click.echo(f"Exporting database in {format} format to {output_dir}...")

        export_db(db_instance, output_dir=output_dir, format=format, split=split)

        if verbose:
            if split:
                click.echo(f"✓ Exported {len(db_instance.indices)} index files (split mode)")
            else:
                click.echo(f"✓ Exported database to db.{format}")
        else:
            click.echo(f"✓ Composed {len(all_samples)} samples")

    except Exception as e:
        raise click.ClickException(f"Compose failed: {e}")


def export_db(db_obj: db.IndexTable, output_dir: str, format: str, split: bool):
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

    file_ext = format

    # Build data structures for all indices
    indices_data = {}
    for index_id, index in db_obj.indices.items():
        samples_dict = {}
        for sample_id, sample in index.samples.items():
            samples_dict[sample_id] = {
                "files": sample.files,
                "kmer_count": sample.kmer_count,
            }

        indices_data[index_id] = {
            "id": index.id,
            "partition_count": index.partition_count,
            "bf_size": index.bf_size,
            "stored_size_bytes": index.stored_size_bytes,
            "stored_size_str": index.stored_size_str,
            "sample_count": index.sample_count,
            "samples": samples_dict,
        }

    # Export to file(s)
    if split:
        # Export each index to its own file
        for index_id, index_data in indices_data.items():
            filepath = os.path.join(output_dir, f"{index_id}.{file_ext}")
            with open(filepath, "w") as f:
                if format == "yaml":
                    yaml.safe_dump(index_data, f, default_flow_style=False)
                else:
                    json.dump(index_data, f, indent=2)
    else:
        # Export all indices to a single file
        db_data = {"indices": indices_data}
        filepath = os.path.join(output_dir, f"db.{file_ext}")
        with open(filepath, "w") as f:
            if format == "yaml":
                yaml.safe_dump(db_data, f, default_flow_style=False)
            else:
                json.dump(db_data, f, indent=2)


def export_span(value, samples):
    pass


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
                click.echo(
                    f"Warning: File k={file_k} does not match CLI k={cli_kmer_size}",
                    err=True,
                )
            if "samples" in data:
                for sample_id, sample_data in data["samples"].items():
                    files = sample_data.get("files", [])
                    if not files:
                        click.echo(
                            f"Warning: Sample {sample_id} has no files, skipping",
                            err=True,
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
                click.echo(
                    f"Warning: File k={file_k} does not match CLI k={cli_kmer_size}",
                    err=True,
                )
            if "samples" in data:
                for sample_id, sample_data in data["samples"].items():
                    files = sample_data.get("files", [])
                    if not files:
                        click.echo(
                            f"Warning: Sample {sample_id} has no files, skipping",
                            err=True,
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
    sample: db.Sample, kmer_size, ntcard_threads, false_positive_rate, verbose, recount=False
):
    click.echo(f"  Process sample {sample.id or sample.files[0]}")

    kc = KmerCounter(k=kmer_size, threadCount=ntcard_threads)
    sm = SpanManager(p=false_positive_rate)

    if sample.kmer_count == 0 or recount:
        if verbose:
            action = "Recounting" if recount else "Counting"
            click.echo(f"  {action} k-mers for sample {sample.id or sample.files[0]}")
        sample.kmer_count = kc.count_files(sample.files)
        if verbose:
            click.echo(f"    k-mer count: {sample.kmer_count}")
    elif verbose:
        click.echo(f"  Using cached k-mer count for sample {sample.id or sample.files[0]}: {sample.kmer_count}")

    span = sm.dispatch(sample.kmer_count)
    bf_size = sm.get_bf_size(span)

    if verbose:
        click.echo(f"    Span: {span}, BF size: {bf_size} bytes")

    if not sample.id:
        filename = os.path.basename(sample.files[0])
        # Remove compression extensions (.gz, .bz2, .zip, etc.)
        if filename.endswith((".gz", ".bz2", ".zip", ".xz")):
            filename = os.path.splitext(filename)[0]
        # Remove file extension
        sample.id = os.path.splitext(filename)[0]
        if verbose:
            click.echo(f"    Generated sample ID from filename: {sample.id}")

    sample.id = db.clean_sample_id(sample.id)
    if verbose:
        click.echo(f"    Final sample ID: {sample.id}")

    return span, bf_size
