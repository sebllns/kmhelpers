"""Recursively list samples from a directory and output a YAML file."""

import hashlib
import os
from datetime import datetime, timezone

import click
import yaml

from pykmhelpers.core.cache import Cache
from pykmhelpers.core.constants import DATA_EXT
from pykmhelpers.core.kmer import KmerCounter
from pykmhelpers.pipeline.index_db import IndexDefinitionTools

# ---------------------------------------------------------------------------
# Sample discovery helpers
# ---------------------------------------------------------------------------


def _collect_samples_grouped(root: str) -> dict[str, list[str]]:
    """Recursively collect samples grouped by leaf folder."""
    samples: dict[str, list[str]] = {}
    tools = IndexDefinitionTools()

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        data_files = []
        for fname in sorted(filenames):
            for ext in DATA_EXT:
                if fname.endswith(ext):
                    data_files.append(os.path.join(dirpath, fname))
                    break

        if data_files:
            folder_name = os.path.basename(dirpath)
            sample_id = tools.clean_sample_id(folder_name)
            if sample_id in samples:
                samples[sample_id].extend(data_files)
            else:
                samples[sample_id] = data_files

    return samples


def _collect_samples_flat(root: str) -> dict[str, list[str]]:
    """Collect all data files under root as individual samples (no grouping)."""
    tools = IndexDefinitionTools()
    samples: dict[str, list[str]] = {}

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for fname in sorted(filenames):
            for ext in DATA_EXT:
                if fname.endswith(ext):
                    filepath = os.path.join(dirpath, fname)
                    base = fname
                    for e in DATA_EXT:
                        if base.endswith(e):
                            base = base[: len(base) - len(e)]
                            break
                    sample_id = tools.clean_sample_id(base)
                    if sample_id in samples:
                        samples[sample_id].append(filepath)
                    else:
                        samples[sample_id] = [filepath]
                    break

    return samples


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

_CACHE_TABLE = "kmer_counts"


def _cache_dir(output_file: str) -> str:
    return Cache.get_cache_dir(
        os.path.dirname(output_file), os.path.basename(output_file)
    )


def _sample_fingerprint(files: list[str], k: int) -> str:
    """Stable fingerprint for a sample: sorted abs paths + mtime + k."""
    h = hashlib.sha1()
    h.update(str(k).encode())
    for f in sorted(files):
        h.update(f.encode())
        try:
            h.update(str(os.path.getmtime(f)).encode())
        except OSError:
            pass
    return h.hexdigest()


# ---------------------------------------------------------------------------
# CLI command
# ---------------------------------------------------------------------------


@click.command(name="list")
@click.option(
    "--input",
    "-i",
    "input_dir",
    required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    help="Input directory to scan recursively for sample files",
)
@click.option(
    "--output",
    "-o",
    "output_file",
    required=True,
    type=click.Path(file_okay=True, dir_okay=False),
    help="Output YAML file path",
)
@click.option(
    "--kmer-size",
    "-k",
    type=int,
    default=25,
    show_default=True,
    help="K-mer size used for counting",
)
@click.option(
    "--count",
    "do_count",
    is_flag=True,
    default=False,
    help="Count k-mers for each sample using ntcard",
)
@click.option(
    "--no-grouping",
    "no_grouping",
    is_flag=True,
    default=False,
    help="Disable grouping by leaf folder; each file becomes its own sample",
)
@click.option(
    "--threads",
    "-t",
    type=int,
    default=8,
    show_default=True,
    help="Number of threads for k-mer counting (only used with --count)",
)
@click.option(
    "--no-cache",
    "no_cache",
    is_flag=True,
    default=False,
    help="Disable the k-mer count cache (always recount every sample)",
)
@click.option(
    "--clear-cache",
    "clear_cache",
    is_flag=True,
    default=False,
    help="Delete any existing cache before running",
)
def list_samples(
    input_dir,
    output_file,
    kmer_size,
    do_count,
    no_grouping,
    threads,
    no_cache,
    clear_cache,
):
    """Recursively list samples from a directory and output a YAML file.

    By default, files are grouped by leaf folder: each leaf directory
    becomes one sample whose ID is the folder name. Use --no-grouping to
    treat every file independently.

    When --count is used, each completed k-mer count is saved to a cache
    file (<output>.cache.yaml) so an interrupted run can resume without
    recounting already-finished samples. The cache is deleted automatically
    on successful completion. Use --no-cache to skip caching entirely or
    --clear-cache to discard a previous partial run.
    """
    input_dir = os.path.abspath(input_dir)

    if no_grouping:
        samples = _collect_samples_flat(input_dir)
    else:
        samples = _collect_samples_grouped(input_dir)

    if not samples:
        raise click.ClickException(f"No data files found under {input_dir}")

    counter = None
    if do_count:
        try:
            counter = KmerCounter(k=kmer_size, threadCount=threads)
        except FileNotFoundError as e:
            raise click.ClickException(str(e))

    # Cache setup (only meaningful when counting)
    cache_dir = _cache_dir(output_file)
    use_cache = do_count and not no_cache

    cache: Cache | None = None
    cached_counts: dict[str, str] = {}

    if use_cache:
        if clear_cache:
            import shutil

            if os.path.exists(cache_dir):
                shutil.rmtree(cache_dir)
                click.echo(f"Cache cleared: {cache_dir}")
        cache = Cache(cache_dir)
        cached_counts = cache.read(_CACHE_TABLE)  # read before opening append handle

    samples_out: dict = {}
    sorted_ids = sorted(samples.keys())
    total = len(sorted_ids)

    for idx, sample_id in enumerate(sorted_ids, 1):
        files = samples[sample_id]

        # Relative paths for output
        rel_files = []
        for f in files:
            try:
                rel_files.append(os.path.relpath(f, start=os.path.dirname(input_dir)))
            except ValueError:
                rel_files.append(f)

        kmer_count = 0

        if counter is not None:
            fingerprint = _sample_fingerprint(files, kmer_size)

            if use_cache and fingerprint in cached_counts:
                kmer_count = int(cached_counts[fingerprint])
                click.echo(f"[{idx}/{total}] {sample_id}: cached ({kmer_count})")
            else:
                try:
                    click.echo(f"[{idx}/{total}] {sample_id}: counting...", nl=False)
                    kmer_count = counter.count_files(files)
                    click.echo(f" {kmer_count}")

                    if cache is not None:
                        cache.write(_CACHE_TABLE, fingerprint, str(kmer_count))

                except Exception as e:
                    click.echo("")  # newline after the "counting..." line
                    kmer_count = 0
                    click.echo(
                        f"Warning: could not count k-mers for {sample_id}: {e}",
                        err=True,
                    )

        entry: dict = {"files": rel_files}
        if do_count:
            entry = {"kmer_count": kmer_count, "files": rel_files}

        samples_out[sample_id] = entry

    doc = {
        "description": "generated by kmhelpers",
        "date": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f"),
        "total_samples": len(samples_out),
        "k": kmer_size,
        "samples": samples_out,
    }

    with open(output_file, "w") as fh:
        yaml.dump(doc, fh, default_flow_style=False, sort_keys=False)

    click.echo(f"Listed {len(samples_out)} samples -> {output_file}")

    # Close open handles then remove the cache dir on clean completion
    if cache is not None:
        cache.delete()
