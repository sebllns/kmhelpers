"""``--show-progress``: one line per shard, redrawn as the build goes.

::

    ⣾ idx_g0  [■■■■■■      ] 6/11 (8m3s)   3 running: chunk2 (4m10s), chunk5 (3m12s), chunk8 (52s)
    ✔ idx_g1  [■■■■■■■■■■■■] 8/8  (25m14s) SUCCESS
    ✘ idx_g2  [■■■         ] 3/9  (6m2s)   FAILED chunk3 (log: logs/idx_g2/...)

Shards not started are not shown. In a terminal (``live``), the lines are
redrawn in place, with colors; otherwise a shard's line is printed when it
changes (a step starts or ends, the shard ends).

``detailed`` (``--task``): in a terminal, each running step gets a line under
its shard, with its job, its RAM and the current kmtricks phase::

    ⣾ idx_g0  [■■■■■■      ] 6/11 (8m3s)   chunk5 (3m12s)
        └ chunk5  job 179709_5 @node58  RAM 45.6G/120G (38%)  Count partitions [■■■■■■■     ] 63%
"""

import logging
import sys
import threading
from datetime import datetime
from typing import Callable, Optional

from pykmhelpers.pipeline.index_ops.status import (
    RUNNING,
    BuildState,
    ShardProgress,
    StepDetail,
    detail_text,
    kmtricks_phase,
    shard_line,
    shard_progress,
    short_step,
    step_details,
)

SPINNER = ["⢿", "⣻", "⣽", "⣾", "⣷", "⣯", "⣟", "⡿"]
TICK = 0.5  # seconds between two redraws in a terminal
PHASE_TICKS = 4  # ticks between two reads of the logs of the running steps (detailed)


class ShardDisplay:
    """The shards of ``tasks`` (part names), drawn on ``stream``.

    ``update()`` reads the steps again (after a state change, or each poll of
    a watch); in a terminal, a thread redraws every ``TICK`` the spinner and
    the clocks from what was read last. ``detailed``: the running steps too
    (see ``step_details``; ``ram`` measures them, or ``set_ram`` is told).
    """

    def __init__(
        self,
        state: BuildState,
        tasks: Optional[list[str]] = None,
        live: Optional[bool] = None,
        stream=None,
        alive: Optional[Callable[[str], Optional[bool]]] = None,
        detailed: bool = False,
        ram: Optional[Callable[[dict], Optional[tuple]]] = None,
    ) -> None:
        self.state = state
        self.tasks = [t for t in (tasks or list(state.tasks)) if t in state.tasks]
        self.stream = stream or sys.stdout
        self.live = self.stream.isatty() if live is None else live
        self.alive = alive
        self.width = max((len(state.tasks[t]["shard"]) for t in self.tasks), default=0)
        self.shards: list[ShardProgress] = []
        self.detailed = detailed
        self.ram = ram
        self.details: dict[str, list[StepDetail]] = {}  # shard -> running steps
        self._pushed: dict[tuple[str, str], tuple] = {}  # (shard, step) -> set_ram
        self._printed: dict[str, tuple] = {}
        self._height = 0
        self._frame = 0
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._logs: list[tuple[logging.Handler, logging.Handler]] = []

    # --- lifecycle

    def start(self) -> "ShardDisplay":
        self.update()
        if self.live:
            self._wrap_logs()
            self._thread = threading.Thread(target=self._tick, daemon=True)
            self._thread.start()
        return self

    def close(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join()
        self.update()
        self._unwrap_logs()

    def __enter__(self) -> "ShardDisplay":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.close()

    # --- drawing

    def update(self) -> list[ShardProgress]:
        """Read the shards again, and draw them."""
        submitted = self.state.submitted()
        shards = [
            shard_progress(self.state, self.state.tasks[t], self.alive, submitted)
            for t in self.tasks
        ]
        details = {}
        if self.detailed and self.live:
            for t, p in zip(self.tasks, shards):
                running = {s for s, _ in p.running}
                if running:
                    details[p.shard] = step_details(
                        self.state, self.state.tasks[t], running, self.alive, submitted, self.ram
                    )
        with self._lock:
            self.shards = shards
            self.details = details
            self._pushed = {
                k: v for k, v in self._pushed.items()
                if any(d.step == k[1] for d in details.get(k[0], []))
            }
            if self.live:
                self._redraw()
            else:
                self._print_changes()
        return shards

    def lines(self, now: Optional[datetime] = None) -> list[str]:
        now = now or datetime.now()
        spinner = SPINNER[self._frame % len(SPINNER)]
        lines = []
        for p in self.shards:
            if not p.shown:
                continue
            lines.append(shard_line(p, self.width, now, spinner, color=self.live))
            for d in self.details.get(p.shard, []):
                if d.status != RUNNING:
                    continue
                d.ram = self._pushed.get((p.shard, d.step), d.ram)
                text = detail_text(d, now, color=self.live, live=True)
                lines.append(f"    └ {short_step(d.step)}  {text}".rstrip())
        return lines or [f"{spinner} {self.waiting_message()}"]

    def set_ram(self, shard: str, step: str, used: int, budget: Optional[int] = None) -> None:
        """RAM of a running step, measured by its runner; drawn at the next tick."""
        with self._lock:
            self._pushed[(shard, step)] = (used, budget)

    def waiting_message(self) -> str:
        """Shown while no shard has started (jobs queued, or about to run)."""
        n = len(self.shards)
        return f"waiting for the first step to start ({n} shard{'s' if n != 1 else ''} pending)"

    def _tick(self) -> None:
        while not self._stop.wait(TICK):
            with self._lock:
                self._frame += 1
                if self.details and self._frame % PHASE_TICKS == 0:
                    for d in (d for ds in self.details.values() for d in ds):
                        d.phase = kmtricks_phase(d.log) or d.phase
                self._redraw()

    def _erase(self) -> None:
        if self._height:
            # up to the first drawn line, and clear down
            self.stream.write(f"\033[{self._height}F\033[J")
            self._height = 0

    def _redraw(self) -> None:
        lines = self.lines()
        self._erase()
        if lines:
            self.stream.write("\n".join(lines) + "\n")
        self._height = len(lines)
        self.stream.flush()

    def _print_changes(self) -> None:
        now = datetime.now()
        if self.shards and not any(p.shown for p in self.shards) and not self._printed:
            # once, not redrawn
            self._printed[""] = ()
            self.stream.write(f"- {self.waiting_message()}\n")
        for p in self.shards:
            if p.shown and self._printed.get(p.shard) != p.key():
                self._printed[p.shard] = p.key()
                # printed once per change: no spinner, no running steps
                idle = ShardProgress(**{**p.__dict__, "running": []})
                self.stream.write(shard_line(idle, self.width, now, spinner="") + "\n")
        self.stream.flush()

    # --- log lines go above the drawn lines

    def _wrap_logs(self) -> None:
        root = logging.getLogger()
        for handler in list(root.handlers):
            if isinstance(handler, logging.StreamHandler) and getattr(
                handler.stream, "isatty", lambda: False
            )():
                proxy = _AboveDisplay(handler, self)
                root.removeHandler(handler)
                root.addHandler(proxy)
                self._logs.append((handler, proxy))

    def _unwrap_logs(self) -> None:
        root = logging.getLogger()
        for handler, proxy in self._logs:
            root.removeHandler(proxy)
            root.addHandler(handler)
        self._logs = []


class _AboveDisplay(logging.Handler):
    """Emit through ``inner``, erasing the display first and redrawing it after."""

    def __init__(self, inner: logging.Handler, display: ShardDisplay) -> None:
        super().__init__(inner.level)
        self.inner = inner
        self.display = display

    def emit(self, record: logging.LogRecord) -> None:
        with self.display._lock:
            self.display._erase()
            self.display.stream.flush()
            self.inner.handle(record)
            self.display._redraw()
