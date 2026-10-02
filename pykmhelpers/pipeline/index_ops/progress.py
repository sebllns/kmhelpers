import threading
from datetime import datetime
from time import sleep

from pykmhelpers.operations.builder import IndexBuilder
from pykmhelpers.pipeline.index_ops.types import ApplyMode


class NullProgress:
    """No-op progress display, used when progress is not shown."""

    handler = None

    def __enter__(self) -> "NullProgress":
        return self

    def __exit__(self, *exc) -> None:
        pass


class ProgressDisplay:
    """Terminal progress for one build: a spinner until the first progress
    estimate arrives, then a progress bar.

    Used as a context manager; ``handler`` is passed to
    ``IndexBuilder.create_subindex``.
    """

    SPINNER = ["⢿", "⣻", "⣽", "⣾", "⣷", "⣯", "⣟", "⡿"]
    BAR_LEN = 30

    def __init__(self, name: str) -> None:
        self._name = name
        self._start = datetime.now()
        self._stop = threading.Event()
        self._spinner = threading.Thread(target=self._spin, daemon=True)
        self.handler: IndexBuilder.Progress | None = None

    def __enter__(self) -> "ProgressDisplay":
        self._start = datetime.now()
        self._spinner.start()
        self.handler = IndexBuilder.Progress(self._on_progress, delay=60)
        return self

    def __exit__(self, *exc) -> None:
        self._stop_spinner()

    def _stop_spinner(self) -> None:
        self._stop.set()
        self._spinner.join()

    def _spin(self) -> None:
        sleep(2)
        s = 0
        while not self._stop.wait(timeout=0.5):
            print(
                f"\r\033[1;32m{self.SPINNER[s]} Building index '{self._name}'...\033[0m ",
                end="",
                flush=True,
            )
            s = (s + 1) % len(self.SPINNER)

    def _on_progress(self, value: float) -> None:
        elapsed = (datetime.now() - self._start).total_seconds()
        filled = int(round(self.BAR_LEN * value))
        bar = "■" * filled + " " * (self.BAR_LEN - filled)
        print(
            f"\r[{bar}] {value * 100:.1f}%  elapsed: {int(elapsed // 60)}m{int(elapsed % 60):02d}s      ",
            end="",
            flush=True,
        )
        self._stop_spinner()


def progress_for(mode: ApplyMode, name: str) -> ProgressDisplay | NullProgress:
    if mode is ApplyMode.APPLY_SHOW_PROGRESS:
        return ProgressDisplay(name)
    return NullProgress()
