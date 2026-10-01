"""Draw the state of a build directory against its compose definitions."""

import json
import logging

import click

from pykmhelpers.pipeline.index_map import build_map, render_figure, render_text

logger = logging.getLogger(__name__)


@click.command(name="map")
@click.argument(
    "build_dir",
    nargs=1,
    required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
)
@click.option(
    "--compose-dir",
    "-c",
    "compose_dir",
    required=False,
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    help="COMPOSE_DIR holding NAME/SESSION/*.yaml definitions, to show declared but missing indices.",
)
@click.option(
    "--output",
    "-o",
    "output_file",
    required=False,
    type=click.Path(dir_okay=False),
    help="Write the map as an image (format from extension: .svg, .png, .pdf).",
)
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    default=False,
    help="Print the collected map as JSON instead of a table.",
)
def map_cmd(build_dir, compose_dir, output_file, output_json):
    """Show the state of the indices in BUILD_DIR, one row per index, one column per session.

    \b
    Input:  BUILD_DIR (build -o), optional COMPOSE_DIR (-c)
    Output: table on stdout, optional image (-o)

    \b
    Cell status:
      active      built, currently registered version
      superseded  built, replaced by a later session
      missing     declared in COMPOSE_DIR, not built
      orphan      built, not declared in COMPOSE_DIR (requires -c)
      broken      registered, but its data folder is missing
    """
    try:
        index_map = build_map(build_dir, compose_dir)
    except FileNotFoundError as e:
        raise click.ClickException(str(e))
    except ValueError as e:
        raise click.UsageError(str(e))

    if output_json:
        click.echo(json.dumps(index_map.to_dict(), indent=2))
    else:
        click.echo(render_text(index_map))

    if output_file:
        render_figure(index_map, output_file)
        logger.info(f"Map written to {output_file}")
