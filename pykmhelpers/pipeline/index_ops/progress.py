"""``--show-progress``: one line per shard, redrawn as the build goes.

::

    ⣾ idx_g0  [■■■■■■      ] 6/11 (8m3s)   3 running: chunk2 (4m10s), chunk5 (3m12s), chunk8 (52s)
    ✔ idx_g1  [■■■■■■■■■■■■] 8/8  (25m14s) SUCCESS
    ✘ idx_g2  [■■■         ] 3/9  (6m2s)   FAILED chunk3 (log: logs/idx_g2/...)

Shards not started are not shown. In a terminal (``live``), the lines are
redrawn in place, with colors; otherwise a shard's line is printed when it
changes (a step starts or ends, the shard ends).
"""

import logging
import sys
import threading
from datetime import datetime
from typing import Callable, Optional

from pykmhelpers.pipeline.index_ops.status import (
    BuildState,
    ShardProgress,
    shard_line,
    shard_progress,
)

SPINNER = ["⢿", "⣻", "⣽", "⣾", "⣷", "⣯", "⣟", "⡿"]
TICK = 0.5  # seconds between two redraws in a terminal


class ShardDisplay:
    """The shards of ``tasks`` (part names), drawn on ``stream``.

    ``update()`` reads the steps again (after a state change, or each poll of
    a watch); in a terminal, a thread redraws every ``TICK`` the spinner and
    the clocks from what was read last.
    """

    def __init__(
        self,
        state: BuildState,
        tasks: Optional[list[str]] = None,
        live: Optional[bool] = None,
        stream=None,
        alive: Optional[Callable[[str], Optional[bool]]] = None,
    ) -> None:
        self.state = state
        self.tasks = [t for t in (tasks or list(state.tasks)) if t in state.tasks]
        self.stream = stream or sys.stdout
        self.live = self.stream.isatty() if live is None else live
        self.alive = alive
        self.width = max((len(state.tasks[t]["shard"]) for t in self.tasks), default=0)
        self.shards: list[ShardProgress] = []
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
        with self._lock:
            self.shards = shards
            if self.live:
                self._redraw()
            else:
                self._print_changes()
        return shards

    def lines(self, now: Optional[datetime] = None) -> list[str]:
        now = now or datetime.now()
        spinner = SPINNER[self._frame % len(SPINNER)]
        lines = [
            shard_line(p, self.width, now, spinner, color=self.live)
            for p in self.shards
            if p.shown
        ]
        return lines or [f"{spinner} {self.waiting_message()}"]

    def waiting_message(self) -> str:
        """Shown while no shard has started (jobs queued, or about to run)."""
        n = len(self.shards)
        return f"waiting for the first step to start ({n} shard{'s' if n != 1 else ''} pending)"

    def _tick(self) -> None:
        while not self._stop.wait(TICK):
            with self._lock:
                self._frame += 1
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
