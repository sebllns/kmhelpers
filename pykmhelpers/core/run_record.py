"""What a command was run with: the ``run`` block of the reports, and the
``history.tsv`` of a folder.

The ``run`` block holds the command line, the folder it was run from, the
command as a step of a ``kmhelpers pipeline`` file (the options given, so
``kmhelpers pipeline <report>`` runs it again) and the defaults that applied.
A command a ``pipeline`` runs gets no step: its pipeline file is the record.
"""

import logging
import os
import platform
import shlex
import sys
import time
from datetime import datetime
from typing import Any, Optional

import click
import yaml
from click.core import ParameterSource

from pykmhelpers.core.constants import KMHELPERS_COMMIT, KMHELPERS_VERSION

logger = logging.getLogger(__name__)

HISTORY_FILE = "history.tsv"
HISTORY_HEADER = "time\treport\tstatus\tduration_s\tcommand\n"

# Options that only act on this run, or only display: not in the replayed step
# (--redesign and --replan would remove a design or a plan again)
ONE_SHOT = frozenset(
    {"help", "redesign", "replan", "pending", "status", "do_cleanup", "interval", "show_progress"}
)


def _plain(value: Any) -> Any:
    """A value YAML writes as is: tuples as lists, paths as strings."""
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def _defaulted(ctx: click.Context, name: Optional[str]) -> bool:
    return not name or ctx.get_parameter_source(name) in (None, ParameterSource.DEFAULT)


def command_line() -> str:
    """The command line, as typed."""
    return shlex.join(["kmhelpers", *sys.argv[1:]])


def run_record(ctx: Optional[click.Context] = None) -> Optional[dict]:
    """The ``run`` block of the command being run (the current click context),
    None outside a command (Python API)."""
    ctx = ctx or click.get_current_context(silent=True)
    if ctx is None or ctx.command is None:
        return None
    record: dict = {"command": command_line(), "cwd": os.getcwd()}
    caller = ctx.parent
    if caller is not None and caller.parent is not None:
        # run by another command (a pipeline step): its file is the record
        record["via"] = caller.info_name
        source = caller.params.get("pipeline_file")
        if source:
            record["pipeline"] = os.path.abspath(source)
    else:
        given, defaults = {}, {}
        for param in ctx.command.params:
            name = param.name
            if name is None or name == "help" or name not in ctx.params:
                continue
            value = _plain(ctx.params[name])
            if _defaulted(ctx, name):
                defaults[name] = value
            elif name not in ONE_SHOT:
                given[name] = value
        record["step"] = [{ctx.command.name: given}]
        record["defaults"] = defaults
    options = global_options(ctx)
    if options:
        record["globals"] = options
    return record


def global_options(ctx: click.Context) -> dict:
    """The options of ``kmhelpers`` itself given before the command (``-Y``,
    ``-V``, ``-C FILE``...). The values of a ``-C`` file are in the step already."""
    root = ctx.find_root()
    if root is ctx:
        return {}
    return {
        name: _plain(value)
        for name, value in root.params.items()
        if name not in ("help", "version") and not _defaulted(root, name)
    }


def step_of(data: Any) -> Optional[list]:
    """The pipeline step of a report (its ``run.step``), None for another file."""
    if isinstance(data, dict) and isinstance(data.get("run"), dict):
        step = data["run"].get("step")
        if isinstance(step, list):
            return step
    return None


def slurm_job() -> Optional[str]:
    array, task = os.environ.get("SLURM_ARRAY_JOB_ID"), os.environ.get("SLURM_ARRAY_TASK_ID")
    if array and task:
        return f"{array}_{task}"
    return os.environ.get("SLURM_JOB_ID")


def append_history(folder: str, report: str, status: str, duration_s: float, command: str) -> None:
    """One line in ``folder/history.tsv``: when, which report (``design``,
    ``plan``, ``apply``: a ``build`` writes both of the last two), status,
    duration, command."""
    path = os.path.join(folder, HISTORY_FILE)
    when = datetime.now().isoformat(timespec="seconds")
    line = f"{when}\t{report}\t{status}\t{duration_s:.1f}\t{command}\n"
    try:
        os.makedirs(folder, exist_ok=True)
        new = not os.path.exists(path)
        # one write of one line: jobs writing at once do not mix their lines
        with open(path, "a") as f:
            f.write((HISTORY_HEADER if new else "") + line)
    except OSError as e:
        logger.warning(f"Could not write {path}: {e}")


class CommandLog:
    """The report of a command that is not ``plan``/``apply``: its ``run``
    block, steps and summary in ``log_dir/kmhelpers_<command>_<stamp>.yaml``,
    written as it goes, and a line in ``log_dir/history.tsv`` at the end."""

    def __init__(self, log_dir: str, command: str, ctx: Optional[click.Context] = None) -> None:
        self.log_dir = log_dir
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.path = os.path.join(log_dir, f"kmhelpers_{command}_{stamp}.yaml")
        self._start = time.monotonic()
        self._current: Optional[tuple] = None  # the step under way, and when it began
        run = run_record(ctx) or {}
        self.details: dict = {
            "summary": {
                "command": command,
                "status": "RUNNING",
                "started": datetime.now().isoformat(timespec="seconds"),
            },
            "run": {
                **run,
                "kmhelpers": {"version": KMHELPERS_VERSION, "commit": KMHELPERS_COMMIT},
                "host": platform.node(),
                **({"slurm_job": slurm_job()} if slurm_job() else {}),
            },
            "steps": {},
        }

    def begin(self, name: str) -> None:
        """Step ``name`` starts: if the command fails before its end, ``close``
        records it as the step that failed."""
        self._current = (name, time.monotonic())

    def step(self, name: str, status: str, **info: Any) -> None:
        """Record the end of step ``name`` (begun with ``begin``)."""
        began = self._current[1] if self._current and self._current[0] == name else time.monotonic()
        self._current = None
        self.details["steps"][name] = {
            "status": status,
            "duration_s": round(time.monotonic() - began, 1),
            **_plain(info),
        }
        self.dump()

    def close(self, status: str, error: Optional[str] = None, **summary: Any) -> None:
        """End the report with ``status``; on a failure, ``error`` goes to the
        step under way, if any."""
        if self._current and status != "SUCCESS":
            self.step(self._current[0], status, **({"error": error} if error else {}))
        duration = round(time.monotonic() - self._start, 1)
        self.details["summary"].update(
            status=status,
            finished=datetime.now().isoformat(timespec="seconds"),
            duration_s=duration,
            **({"error": error} if error else {}),
            **_plain(summary),
        )
        self.dump()
        append_history(
            self.log_dir, self.details["summary"]["command"], status, duration,
            self.details["run"].get("command", ""),
        )

    def dump(self) -> None:
        try:
            os.makedirs(self.log_dir, exist_ok=True)
            with open(self.path, "w") as f:
                yaml.safe_dump(self.details, f, default_flow_style=False, sort_keys=False, width=1 << 16)
        except OSError as e:
            logger.warning(f"Could not write the report {self.path}: {e}")
