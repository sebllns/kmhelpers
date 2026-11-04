"""K-mer index registry management commands."""

import errno
import json
import logging
import os
import shutil

import click

from pykmhelpers import KmindexRegistry, KmtricksIndex
from pykmhelpers.cli.shared import confirm
from pykmhelpers.core.bloom_filter import BloomFilterSpecs
from pykmhelpers.core.byte import ByteCounter
from pykmhelpers.pipeline.index_ops.clean import (
    active_sessions,
    finished_assets,
    log_files,
    path_bytes,
    shard_leftovers,
)
from pykmhelpers.pipeline.index_ops.rename import (
    check_layout_rename,
    index_shards,
    rename_layout,
    rename_shards,
    renamed,
)
from pykmhelpers.pipeline.index_ops.repair import REMOVE, apply_repairs, check_json, plan_repairs
from pykmhelpers.pipeline.index_ops.stats import (
    FPR_WARN,
    write_run_stats,
    write_shard_stats,
)
from pykmhelpers.pipeline.query_check import MIN_GAP, NEG_COUNT, NEG_LENGTH, query_check

logger = logging.getLogger(__name__)

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
@click.option(
    "--autorepair",
    is_flag=True,
    help="Repair the root path and the links of index.json first, relink lost "
    "shards, drop the ones found nowhere (index.json is backed up)",
)
@click.option(
    "--search",
    "search_dirs",
    multiple=True,
    type=click.Path(exists=True, file_okay=False),
    help="With --autorepair: also look for lost shards in DIR (DIR/<name>, DIR/*/<name>)",
)
@click.pass_context
def registry_check(ctx, verbose, index_ids, no_query, zvalue, min_gap, autorepair, search_dirs):
    """Validate registry consistency and check all index structures.

    index.json is checked first: its root path must lead to the registry,
    shard links must be absolute and the samples of a shard must match its
    kmtricks.fof.

    Then, unless --no-query, queries 10 random (k+z)-mers of each shard's first
    sample (positives) and 10 random DNA sequences of 1000 bases (negatives)
    against the registry. It reports the score of that sample on the positives
    and the mean score of the samples on the negatives (empirical FP rate),
    next to the expected one when the build recorded it (--fpr-stats).

    A shard whose positive score is not --min-gap above its negative score is
    broken and fails the check, as does a failing query. A high FP rate is
    only reported.

    With --autorepair, the registry is repaired before the checks: the root
    path of index.json, relative links made absolute, a lost shard linked to
    a folder holding its samples (in the old registry path, work/*/previous/
    or a --search DIR), a shard found nowhere removed from index.json (after
    a confirmation). index.json is first copied to index.json.<time>.bak.
    """
    registry_path = ctx.obj["registry_path"]
    if search_dirs and not autorepair:
        raise click.ClickException("--search needs --autorepair")

    try:
        registry = KmindexRegistry(registry_path, auto_create=False)
        indices = registry.list_indices()
        if index_ids:
            missing = [i for i in index_ids if i not in indices]
            if missing:
                raise click.ClickException(f"Not registered: {', '.join(missing)}")
            indices = list(index_ids)

        repair_errors = []
        if autorepair:
            repair_errors = _autorepair(ctx, registry_path, indices, search_dirs)
            registry.load_json()
            indices = [i for i in indices if registry.has_index(i)]

        if not indices:
            click.echo("No indices found in registry")
            if repair_errors:
                raise click.ClickException(f"{len(repair_errors)} repair(s) failed")
            return

        errors = [("repair", e) for e in repair_errors]
        json_problems = {}
        for name, msg in check_json(registry_path, indices):
            json_problems.setdefault(name, []).append(msg)
        hint = "" if autorepair else " (--autorepair fixes it)"
        for msg in json_problems.pop("index.json", []):
            errors.append(("index.json", msg))
            click.echo(f"✗ index.json: {msg}{hint}", err=True)

        click.echo(f"Validating {len(indices)} index(ices)...\n")

        for idx_name in indices:
            try:
                index = registry.get_index(idx_name)
                if idx_name in json_problems:
                    for msg in json_problems[idx_name]:
                        errors.append((idx_name, msg))
                        click.echo(f"✗ {idx_name}: {msg}", err=True)
                elif index.check_structure():
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

        failed = {name for name, _ in errors if name in indices}
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


def _autorepair(ctx, registry_path: str, shards: list[str], search_dirs) -> list[str]:
    """Plan, print and apply the repairs of the registry; return the errors."""
    repairs, unregistered = plan_repairs(registry_path, shards, search_dirs)
    for name in unregistered:
        click.echo(f"⊙ {name}: index folder not registered (kmhelpers manage add)")
    if not repairs:
        click.echo("Nothing to repair\n")
        return []
    click.echo("Repairs:")
    for r in repairs:
        click.echo(f"  {r}")
    removed = [r.shard for r in repairs if r.kind == REMOVE]
    if removed and not confirm(ctx, f"Remove {len(removed)} lost shard(s) from index.json?"):
        click.echo("Removal cancelled: lost shards kept")
        repairs = [r for r in repairs if r.kind != REMOVE]
    backup, errors = apply_repairs(registry_path, repairs)
    if backup:
        click.echo(f"✓ index.json backed up to {backup}")
    for e in errors:
        click.echo(f"✗ {e}", err=True)
    click.echo(f"✓ {len(repairs) - len(errors)} repair(s) applied\n")
    return errors


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
@click.argument("old")
@click.argument("new")
@click.option(
    "--index",
    "whole_index",
    is_flag=True,
    help="OLD and NEW are index names: rename every shard OLD_g<k>[_p<j>] to NEW_g<k>[_p<j>]",
)
@click.option(
    "--compose-dir",
    type=click.Path(exists=True, file_okay=False),
    help="With --index: also rename COMPOSE_DIR/OLD/ and the shard names of its layout",
)
@click.pass_context
def registry_rename(ctx, old, new, whole_index, compose_dir):
    """Rename the shard OLD to NEW, or with --index the index OLD to NEW.

    The shard folder (or its symlink) and its index.json entry are renamed,
    with its logs and stats (logs/<shard>/); no data is moved or rebuilt.
    index.json is first copied to index.json.<time>.bak. Refused while a
    build of the registry runs or still has a renamed shard to publish.

    With --index, every shard of the index is renamed at once; --compose-dir
    renames its compose folder and the names its layout records, so the next
    compose of NEW updates the renamed shards.
    """
    registry_path = ctx.obj["registry_path"]
    if compose_dir and not whole_index:
        raise click.ClickException("--compose-dir needs --index")
    try:
        registry = KmindexRegistry(registry_path, auto_create=False)
    except Exception as e:
        raise click.ClickException(f"Cannot open the registry: {e}")

    if whole_index:
        shards = index_shards(registry.list_indices(), old)
        if not shards:
            raise click.ClickException(f"No shard of index '{old}' ({old}_g<k>[_p<j>]) in the registry")
        renames = {s: renamed(s, old, new) for s in shards}
    else:
        renames = {old: new}

    if compose_dir:
        try:
            check_layout_rename(compose_dir, old, new)
        except ValueError as e:
            raise click.ClickException(str(e))
    for src, dst in renames.items():
        click.echo(f"  {src} -> {dst}")
    if whole_index and not confirm(ctx, f"Rename {len(renames)} shard(s) of index '{old}' to '{new}'?"):
        click.echo("Operation cancelled")
        return
    try:
        backup = rename_shards(registry_path, renames)
    except (OSError, ValueError) as e:
        raise click.ClickException(f"Rename failed: {e}")
    click.echo(f"✓ index.json backed up to {backup}")
    click.echo(f"✓ Renamed {len(renames)} shard(s)")

    if compose_dir:
        try:
            layout = rename_layout(compose_dir, old, new)
        except (OSError, ValueError) as e:
            raise click.ClickException(
                f"Shards renamed, but not the compose folder {os.path.join(compose_dir, old)}: {e}"
            )
        dst = os.path.join(compose_dir, new)
        click.echo(f"✓ Compose folder renamed: {dst}" + ("" if layout else " (no layout)"))
    elif whole_index:
        click.echo(
            f"⚠ The compose layout of '{old}' still names the old shards: "
            "pass --compose-dir to rename it too",
            err=True,
        )


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


@registry.command(name="clean")
@click.option(
    "--sh",
    "--shard",
    "index_ids",
    multiple=True,
    help="Clean only these shards (default: all); fails if one is not registered",
)
@click.option("--assets", is_flag=True, help="Also remove assets/<session>/ of the finished sessions")
@click.option("--logs", is_flag=True, help="Also remove the logs and reports of logs/ (stats are kept)")
@click.option("--dry-run", "-n", is_flag=True, help="Only list what would be removed")
@click.pass_context
def registry_clean(ctx, index_ids, assets, logs, dry_run):
    """Remove what the published shards and finished builds no longer need.

    In each shard: the kmtricks build intermediates (superkmers/, counts/,
    minimizers/, partition_infos/, merge_infos/, histograms/, filters/,
    howde_index/), read neither by kmindex nor by kmhelpers once built.

    With --assets: assets/<session>/ (plan, scripts, progress) of each session
    whose shards are all published and that has no job left. With --logs: the
    run and publish logs, logs/slurm/ and the kmhelpers_*.yaml reports; the
    stats (stats.yaml, <run>.stats.json) stay. Refused while a job runs.
    """
    registry_path = ctx.obj["registry_path"]
    build_dir = os.path.realpath(registry_path)
    try:
        registry = KmindexRegistry(registry_path, auto_create=False)
    except Exception as e:
        raise click.ClickException(f"Cannot open the registry: {e}")

    shards = registry.list_indices()
    if index_ids:
        missing = [i for i in index_ids if i not in shards]
        if missing:
            raise click.ClickException(f"Not registered: {', '.join(missing)}")
        shards = list(index_ids)

    targets = shard_leftovers(registry, shards)
    if assets:
        removable, kept = finished_assets(build_dir)
        targets += removable
        for session, why in kept.items():
            click.echo(f"⊙ Kept assets/{session}: {why}")
    if logs:
        active = active_sessions(build_dir)
        if active:
            raise click.ClickException(
                f"Jobs still queued or running in session(s) {', '.join(active)}: "
                "not removing the logs"
            )
        targets += log_files(build_dir)

    if not targets:
        click.echo("Nothing to clean")
        return

    sizes = {t: path_bytes(t) for t in targets}
    for t in targets:
        click.echo(f"  {os.path.relpath(t, build_dir)}: {ByteCounter.auto(sizes[t])}")
    total = ByteCounter.auto(sum(sizes.values()))
    click.echo(f"Total: {total}")
    if dry_run:
        return
    if not confirm(ctx, f"Remove {len(targets)} item(s) ({total})?"):
        click.echo("Operation cancelled")
        return

    freed, failed = 0, []
    for t in targets:
        try:
            if os.path.isdir(t) and not os.path.islink(t):
                shutil.rmtree(t)
            else:
                os.remove(t)
            freed += sizes[t]
            logger.info(f"Removed {t}")
        except OSError as e:
            logger.warning(f"Could not remove {t}: {e}")
            failed.append(t)
            click.echo(f"✗ {os.path.relpath(t, build_dir)}: {e}", err=True)
    click.echo(f"Freed {ByteCounter.auto(freed)}")
    if failed:
        raise click.ClickException(f"Could not remove {len(failed)} item(s)")


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
