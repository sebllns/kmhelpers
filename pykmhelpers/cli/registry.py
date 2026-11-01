"""K-mer index registry management commands."""

import errno
import json
import os

import click

from pykmhelpers import KmindexRegistry, KmtricksIndex
from pykmhelpers.cli.shared import confirm
from pykmhelpers.core.bloom_filter import BloomFilterSpecs
from pykmhelpers.core.byte import ByteCounter
from pykmhelpers.pipeline.index_ops.stats import (
    FPR_WARN,
    write_run_stats,
    write_shard_stats,
)
from pykmhelpers.pipeline.query_check import MIN_GAP, NEG_COUNT, NEG_LENGTH, query_check

# (k+z)-mers queried per shard by `check`
QUERY_CHECK_COUNT = 10


@click.group("manage")
@click.option(
    "--registry-path",
    "-r",
    default=".",
    type=click.Path(file_okay=False, dir_okay=True, exists=True, readable=True),
    help="Path to kmindex registry",
)
@click.pass_context
def registry(ctx, registry_path):
    """Manage k-mer index registries."""
    ctx.ensure_object(dict)
    ctx.obj["registry_path"] = registry_path


@registry.command(name="create")
@click.option(
    "--input-dir",
    "-i",
    required=False,
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    help="Input directory containing kmtricks indices",
)
@click.option(
    "--sh",
    "--shard",
    "index_ids",
    multiple=True,
    required=False,
    help="Shard(s) to register (default: all found)",
)
@click.pass_obj
def registry_create(obj, input_dir, index_ids):
    """Register kmtricks indices in a registry."""
    registry_path = obj["registry_path"]

    click.echo("Initializing kmhelpers...")

    if os.path.exists(registry_path):
        raise click.ClickException(f"Path already exixts: {registry_path}")

    registry = KmindexRegistry(registry_path, auto_create=True)

    if input_dir:
        if not os.path.isdir(input_dir):
            raise click.ClickException(f"Path not found: {input_dir}")
        # Get list of indices to register
        if index_ids:
            indices_to_process = index_ids
        else:
            indices_to_process = [
                d
                for d in os.listdir(input_dir)
                if os.path.isdir(os.path.join(input_dir, d))
            ]

        registered = 0
        skipped = 0

        for index_id in indices_to_process:
            try:
                entry_path = os.path.join(input_dir, index_id)
                if not os.path.isdir(entry_path):
                    click.echo(
                        f"Warning: {index_id} is not a directory, skipping", err=True
                    )
                    skipped += 1
                    continue
                if registry.has_index(index_id):
                    click.echo(f"⊙ Already registered: {index_id}")
                    skipped += 1
                    continue
                index = KmtricksIndex(input_dir, index_id)
                index.load_kmtricks_index()
                if index.check_structure():
                    if registry.add_index(index):
                        click.echo(f"✓ Registered: {index_id}")
                        registered += 1
                    else:
                        click.echo(f"✗ Could not register: {index_id}")
                        skipped += 1
                        continue
            except Exception as e:
                click.echo(f"✗ Error processing {index_id}: {e}", err=True)
                skipped += 1

        click.echo(f"\nSummary: {registered} registered, {skipped} skipped")


@registry.command(name="add")
@click.option(
    "--input-dir",
    "-i",
    required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    help="Input directory containing kmtricks indices",
)
@click.option(
    "--sh",
    "--shard",
    "index_ids",
    multiple=True,
    required=False,
    help="Shard(s) to register (default: all found)",
)
@click.pass_obj
def registry_add(obj, input_dir, index_ids):
    """Register kmtricks indices in a registry."""
    registry_path = obj["registry_path"]

    click.echo("Initializing kmhelpers...")

    registry = KmindexRegistry(registry_path, auto_create=False)

    # Get list of indices to register
    if index_ids:
        indices_to_process = index_ids
    else:
        indices_to_process = [
            d
            for d in os.listdir(input_dir)
            if os.path.isdir(os.path.join(input_dir, d))
        ]

    registered = 0
    skipped = 0

    for index_id in indices_to_process:
        try:
            entry_path = os.path.join(input_dir, index_id)
            if not os.path.isdir(entry_path):
                click.echo(
                    f"Warning: {index_id} is not a directory, skipping", err=True
                )
                skipped += 1
                continue
            if registry.has_index(index_id):
                click.echo(f"⊙ Already registered: {index_id}")
                skipped += 1
                continue
            index = KmtricksIndex(input_dir, index_id)
            index.load_kmtricks_index()
            if index.check_structure():
                if registry.add_index(index):
                    click.echo(f"✓ Registered: {index_id}")
                    registered += 1
                else:
                    click.echo(f"✗ Could not register: {index_id}")
                    skipped += 1
                    continue
        except Exception as e:
            click.echo(f"✗ Error processing {index_id}: {e}", err=True)
            skipped += 1

    click.echo(f"\nSummary: {registered} registered, {skipped} skipped")


@registry.command(name="list")
@click.pass_obj
def registry_list(obj):
    """List all indices in a registry."""
    registry_path = obj["registry_path"]

    registry = KmindexRegistry(registry_path, auto_create=False)

    indices = registry.list_indices()
    if not indices:
        click.echo("No indices found in registry")
        return

    click.echo(f"Registry: {registry_path}")
    click.echo(f"Available indices ({len(indices)} total):")
    for idx_name in indices:
        try:
            idx = registry.get_index(idx_name)
            click.echo(
                f"  • {idx_name} ({idx.nb_samples} samples, {idx.nb_partitions} partitions, k={idx.kmer_size})"
            )
        except Exception as e:
            click.echo(f"  ✗ {idx_name}: {e}", err=True)


@registry.command(name="info")
@click.option(
    "--sh",
    "--shard",
    "index_id",
    required=True,
    help="Shard to show information for",
)
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    help="Output as JSON",
)
@click.pass_obj
def registry_info(obj, index_id, output_json):
    """Show detailed information about an index."""
    registry_path = obj["registry_path"]

    try:
        registry = KmindexRegistry(registry_path, auto_create=False)

        if not registry.has_index(index_id):
            raise click.ClickException(f"Index '{index_id}' not found in registry")

        index = registry.get_index(index_id)

        # Data location, resolved through the registry symlink
        data_path = os.path.realpath(index.dir_path)

        # Estimated on-disk size of the Bloom filter matrices
        specs = BloomFilterSpecs(
            n_rows=index.bloom_size,
            n_cols=index.nb_samples,
            n_partitions=index.nb_partitions,
        )
        estimated_size = specs.total_storage_size()

        if output_json:
            # Output as JSON
            data = {
                "index_id": index.id,
                "path": data_path,
                "nb_samples": index.nb_samples,
                "nb_partitions": index.nb_partitions,
                "kmer_size": index.kmer_size,
                "minim_size": index.minim_size,
                "bloom_size": index.bloom_size,
                "bytes_per_row": index.bytes_per_row,
                "index_size": index.index_size,
                "estimated_data_size": estimated_size,
                "kmindex_version": index.kmindex_version,
                "kmtricks_version": index.kmtricks_version,
            }
            click.echo(json.dumps(data, indent=2))
        else:
            # Output as formatted text
            click.echo(f"Index Information: {index_id}")
            click.echo(f"  Path: {data_path}")
            click.echo(f"  Samples: {index.nb_samples}")
            click.echo(f"  Partitions: {index.nb_partitions}")
            click.echo(f"  K-mer size: {index.kmer_size}")
            click.echo(f"  Minimizer size: {index.minim_size}")
            click.echo(f"  Bloom filter size: {index.bloom_size}")
            click.echo(f"  Bytes per row: {index.bytes_per_row}")
            click.echo(f"  Estimated data size: {ByteCounter.auto(estimated_size)}")
            click.echo(f"  kmindex version: {index.kmindex_version}")
            click.echo(f"  kmtricks version: {index.kmtricks_version}")

    except Exception as e:
        raise click.ClickException(f"Failed to retrieve index info: {e}")


@registry.command(name="check")
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show detailed validation output",
)
@click.option(
    "--sh",
    "--shard",
    "index_ids",
    multiple=True,
    help="Check only these shards (default: all); fails if one is not registered",
)
@click.option(
    "--no-query",
    "--nq",
    "no_query",
    is_flag=True,
    help="Skip the query check (random (k+z)-mers of each shard's first sample)",
)
@click.option(
    "--zvalue",
    "-z",
    type=click.IntRange(min=0),
    default=6,
    show_default=True,
    help="Z-value of the query check; its (k+z)-mers are taken from the samples",
)
@click.option(
    "--min-gap",
    type=click.FloatRange(min=0.0, max=1.0),
    default=MIN_GAP,
    show_default=True,
    help="Fail a shard whose positive score minus its negative score is below this",
)
@click.pass_obj
def registry_check(obj, verbose, index_ids, no_query, zvalue, min_gap):
    """Validate registry consistency and check all index structures.

    Then, unless --no-query, queries 10 random (k+z)-mers of each shard's first
    sample (positives) and 10 random DNA sequences of 1000 bases (negatives)
    against the registry. It reports the score of that sample on the positives
    and the mean score of the samples on the negatives (empirical FP rate),
    next to the expected one when the build recorded it (--fpr-stats).

    A shard whose positive score is not --min-gap above its negative score is
    broken and fails the check, as does a failing query. A high FP rate is
    only reported.
    """
    registry_path = obj["registry_path"]

    try:
        registry = KmindexRegistry(registry_path, auto_create=False)
        indices = registry.list_indices()
        if index_ids:
            missing = [i for i in index_ids if i not in indices]
            if missing:
                raise click.ClickException(f"Not registered: {', '.join(missing)}")
            indices = list(index_ids)

        if not indices:
            click.echo("No indices found in registry")
            return

        click.echo(f"Validating {len(indices)} index(ices)...\n")

        errors = []
        for idx_name in indices:
            try:
                index = registry.get_index(idx_name)
                if index.check_structure():
                    click.echo(f"✓ {idx_name}")
                    if verbose:
                        click.echo(
                            f"    {index.nb_partitions} partitions, {index.nb_samples} samples"
                        )
                else:
                    errors.append((idx_name, "Structure check failed"))
                    click.echo(f"✗ {idx_name}: Structure check failed", err=True)
            except Exception as e:
                errors.append((idx_name, str(e)))
                click.echo(f"✗ {idx_name}: {e}", err=True)

        failed = {name for name, _ in errors}
        queried = [i for i in indices if i not in failed]
        if not no_query and queried:
            click.echo(
                f"\nQuery check (z={zvalue}, {QUERY_CHECK_COUNT} (k+z)-mers of each "
                f"shard's first sample, {NEG_COUNT} random sequences of {NEG_LENGTH} bases):"
            )
            try:
                checks = query_check(registry, queried, zvalue, QUERY_CHECK_COUNT)
            except Exception as e:
                errors.append(("query", str(e)))
                click.echo(f"✗ query check failed: {e}", err=True)
                checks = {}
            for name, check in checks.items():
                click.echo(f"  {name}: {check.summary()}")
                if check.broken(min_gap):
                    errors.append((name, "query check failed"))
                    failed.add(name)
                    click.echo(
                        f"✗ {name}: positive score {check.mean:.3f} is not {min_gap} "
                        f"above the negative score {check.neg_mean:.4f}: broken index",
                        err=True,
                    )
                elif check.suspect():
                    click.echo(
                        f"⚠ {name}: empirical FP rate {check.neg_mean:.4f} is far above "
                        f"the expected {check.expected:.4f}",
                        err=True,
                    )

        click.echo()
        if errors:
            query_failed = " (query check failed)" if any(
                name == "query" or msg == "query check failed" for name, msg in errors
            ) else ""
            click.echo(
                f"Validation complete: {len(indices) - len(failed)} OK, "
                f"{len(failed)} FAILED{query_failed}",
                err=True,
            )
            raise click.ClickException(
                f"Registry validation found {len(errors)} error(s)"
            )
        else:
            click.echo(f"Validation complete: All {len(indices)} indices OK")

    except click.ClickException:
        raise
    except Exception as e:
        raise click.ClickException(f"Registry check failed: {e}")


@registry.command(name="remove")
@click.option(
    "--sh",
    "--shard",
    "index_ids",
    multiple=True,
    required=True,
    help="Shard(s) to remove",
)
@click.option(
    "-d",
    "--delete-files",
    is_flag=True,
    help="Also delete index files from disk (destructive!)",
)
@click.option(
    "--missing-ok",
    is_flag=True,
    help="Skip shards that are not registered instead of failing",
)
@click.option(
    "--keep-link",
    is_flag=True,
    help="Only edit index.json: leave a symlinked entry in place",
)
@click.pass_context
def registry_remove(ctx, index_ids, delete_files, missing_ok, keep_link):
    """Remove index from registry (optionally delete files)."""
    registry_path = ctx.obj["registry_path"]

    try:
        registry = KmindexRegistry(registry_path, auto_create=False)

        for index_id in index_ids:
            try:
                if not registry.has_index(index_id):
                    if missing_ok:
                        click.echo(f"⊙ Not registered: {index_id}")
                        continue
                    raise click.ClickException(
                        f"Index '{index_id}' not found in registry"
                    )

                msg = f"Remove '{index_id}' from registry"
                if delete_files:
                    msg += " and delete index files"
                if not confirm(ctx, msg + "?"):
                    click.echo("Operation cancelled")
                    continue
                registry.remove_index(
                    index_id, delete_files=delete_files, keep_link=keep_link
                )
                click.echo(f"✓ Removed '{index_id}' from registry")

            except (click.ClickException, click.Abort):
                raise
            except Exception as e:
                raise click.ClickException(f"Failed to remove index: {e}")
    except (click.ClickException, click.Abort):
        raise
    except Exception as e:
        raise click.ClickException(f"Remove command failed: {e}")


@registry.command(name="rename")
@click.argument("index_id")
@click.argument("new_index_id")
@click.pass_obj
def registry_rename(obj, index_id, new_index_id):
    """Rename the index INDEX_ID to NEW_INDEX_ID."""
    registry_path = obj["registry_path"]

    try:
        registry = KmindexRegistry(registry_path, auto_create=False)

        if not registry.has_index(index_id):
            raise click.ClickException(f"Index '{index_id}' not found in registry")

        if not registry.rename_index(index_id, new_index_id):
            raise click.ClickException(
                f"Could not rename index from '{index_id}' to '{new_index_id}'"
            )

        click.echo(f"✓ Renamed '{index_id}' to '{new_index_id}'")

    except click.ClickException:
        raise
    except Exception as e:
        raise click.ClickException(f"Failed to rename index: {e}")


@registry.command(name="relink")
@click.pass_obj
@click.option(
    "--input-dir",
    "-i",
    required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    help="Input directory containing kmtricks indices",
)
@click.option(
    "--sh",
    "--shard",
    "index_id",
    required=False,
    help="Shard to relink (default: all registered shards)",
)
def registry_relink(obj, input_dir, index_id):
    """Recreate links in an index registry. Useful if links are broken or indices moved."""
    try:
        registry_path = obj["registry_path"]
        click.echo("Relinking...")
        registry = KmindexRegistry(registry_path)
        registry.relink(index_id, input_dir)
    except Exception as e:
        click.ClickException(f"Relink failed: {e}")


# Internal: used by the scripts written by plan/apply/build, not listed in --help
@registry.command(name="move-dir", hidden=True)
@click.argument("source", type=click.Path())
@click.argument("destination", type=click.Path())
@click.option(
    "--missing-ok",
    is_flag=True,
    help="Do nothing if SOURCE does not exist (already moved)",
)
def registry_move(source, destination, missing_ok):
    """Rename SOURCE to DESTINATION, e.g. an index folder of the registry.

    A rename only, so its duration does not depend on the size: it fails,
    instead of copying, when both are not on one filesystem. DESTINATION must
    not exist; its parent folder is created. A symlink is moved, not followed.
    """
    if not os.path.lexists(source):
        if missing_ok:
            click.echo(f"⊙ Already moved: {source}")
            return
        raise click.ClickException(f"Not found: {source}")
    if os.path.lexists(destination):
        raise click.ClickException(f"Already exists: {destination}")
    os.makedirs(os.path.dirname(os.path.abspath(destination)), exist_ok=True)
    try:
        os.rename(source, destination)
    except OSError as e:
        if e.errno == errno.EXDEV:
            raise click.ClickException(
                f"{source} and {destination} are not on the same filesystem: "
                f"not copying"
            )
        raise click.ClickException(f"Move failed: {e}")
    click.echo(f"✓ Moved {source} -> {destination}")


# Internal: written by the chunk scripts of plan/apply/build
@registry.command(name="run-stats", hidden=True)
@click.argument("run_dir", type=click.Path(exists=True, file_okay=False))
@click.argument("out", type=click.Path(dir_okay=False))
@click.option("--fpr", is_flag=True, help="Also read the FP rate of each sample")
def registry_run_stats(run_dir, out, fpr):
    """Write the stats of the kmtricks run RUN_DIR to OUT (JSON)."""
    try:
        stats = write_run_stats(run_dir, out, fpr)
    except Exception as e:
        raise click.ClickException(f"Run stats failed: {e}")
    click.echo(
        f"✓ {stats['run']}: {stats['samples']} samples, {stats.get('duration_s')}s, "
        f"peak RSS {stats.get('peak_rss_mb')} MB, disk {stats['disk_size']}, "
        f"BF {stats['bf_size']}"
    )


# Internal: written by the publish scripts of plan/apply/build
@registry.command(name="shard-stats", hidden=True)
@click.argument("run_stats", nargs=-1, type=click.Path(dir_okay=False))
@click.option("--shard", required=True, help="Published shard")
@click.option("--session", required=True, help="Session the runs were built in")
@click.option("--out", required=True, type=click.Path(dir_okay=False), help="stats.yaml")
@click.option("--publish-seconds", type=float, help="Duration of the publish script")
@click.pass_obj
def registry_shard_stats(obj, run_stats, shard, session, out, publish_seconds):
    """Fold the run stats RUN_STATS of SESSION into the stats of SHARD."""
    shard_dir = os.path.join(obj["registry_path"], shard)
    try:
        data = write_shard_stats(out, shard, session, list(run_stats), publish_seconds, shard_dir)
    except Exception as e:
        raise click.ClickException(f"Shard stats failed: {e}")
    summary = data["summary"]
    click.echo(
        f"✓ {shard}: {summary['samples']} samples, {summary['duration_s']}s, "
        f"peak disk {summary['peak_disk_size']}, disk {summary['disk_size']}"
    )
    above = summary.get("fpr_above_1pct")
    if above:
        click.echo(
            f"⚠ {shard}: {len(above)} sample(s) with an FP rate above {FPR_WARN:.0%}: "
            + ", ".join(above),
            err=True,
        )
