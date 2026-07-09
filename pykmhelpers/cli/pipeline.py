"""Pipeline command - run a sequence of kmhelpers commands from a YAML file."""

import logging

import click
import yaml

from pykmhelpers.core.log import Log

logger = logging.getLogger(__name__)


def _iter_steps(steps):
    """Yield (cmd_name, args_dict) pairs from either format:

    Dict format (no repeated commands):
        apply:
          workdir: /path

    List format (allows repeating the same command):
        - apply:
            workdir: /path
        - apply:
            workdir: /other
    """
    if isinstance(steps, dict):
        yield from steps.items()
    elif isinstance(steps, list):
        for item in steps:
            if not isinstance(item, dict) or len(item) != 1:
                raise click.ClickException(
                    f"Each pipeline list entry must be a single-key mapping, got: {item!r}"
                )
            yield from item.items()
    else:
        raise click.ClickException(
            "Pipeline file must be a YAML mapping or sequence of mappings."
        )


@click.command(name="pipeline")
@click.argument("pipeline_file", type=click.Path(exists=True))
@click.option(
    "-x",
    "extra",
    type=(str, str),
    multiple=True,
    metavar="KEY VALUE",
    help="⚙   Override a parameter for all steps (e.g. -x workdir /tmp -x threads 8). "
    "Takes precedence over both the pipeline file and -C global config.",
)
@click.pass_context
def pipeline(ctx, pipeline_file, extra):
    """Run a sequence of commands defined in a YAML pipeline file.

    PIPELINE_FILE maps command names to their arguments. Steps execute in order.

    \b
    Dict format (simple, no repeated commands):
        compose:
          workdir: /path/to/workdir
          input_file: samples.yaml
        apply:
          workdir: /path/to/workdir
          threads: 8

    \b
    List format (allows repeating the same command):
        - apply:
            workdir: /path/a
            input_file: a.yaml
        - apply:
            workdir: /path/b
            input_file: b.yaml
    """
    with open(pipeline_file) as f:
        steps = yaml.safe_load(f)

    if not steps:
        logger.warning("Pipeline file is empty, nothing to do.")
        return

    # Global config from -C, propagated by Click into ctx.default_map
    global_config = ctx.default_map or {}

    # Parse -x KEY VALUE pairs; values are YAML scalars for correct typing
    extra_kwargs = {k.replace("-", "_"): yaml.safe_load(v) for k, v in extra}

    root_cmd = ctx.find_root().command

    for cmd_name, cmd_args in _iter_steps(steps):
        cmd = root_cmd.get_command(ctx, cmd_name)
        if cmd is None:
            raise click.ClickException(f"Unknown command in pipeline: '{cmd_name}'")

        # Normalize YAML keys: hyphens → underscores to match Click param names
        step_kwargs = {k.replace("-", "_"): v for k, v in (cmd_args or {}).items()}

        # Priority: global config < pipeline YAML < -x overrides
        kwargs = {**global_config, **step_kwargs, **extra_kwargs}

        # Coerce list → tuple for nargs=-1 params (e.g. input_files)
        for param in cmd.params:
            if param.nargs == -1 and param.name in kwargs:
                val = kwargs[param.name]
                kwargs[param.name] = tuple(val) if isinstance(val, list) else (val,)

        logger.info(f"Pipeline step: {cmd_name}")
        try:
            ctx.invoke(cmd, **kwargs)
        except click.ClickException:
            raise
        except Exception as e:
            Log.handle_exception(logger, e, f"FAILED (pipeline step: '{cmd_name}')")
            raise click.ClickException(f"FAILED (pipeline step: '{cmd_name}')")
